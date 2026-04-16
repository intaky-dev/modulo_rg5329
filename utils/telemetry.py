"""
OpenTelemetry instrumentation utilities for modulo_rg5329.

Gracefully degrades to no-ops if the opentelemetry packages are not installed.
The module still works normally — telemetry is additive and optional.

Installation (inside the Odoo virtualenv):
    pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc

Configuration via environment variables:
    OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317   # OTLP/gRPC endpoint
    OTEL_SERVICE_NAME=odoo-rg5329                            # optional override

Development (console output, no extra infra needed):
    Leave OTEL_EXPORTER_OTLP_ENDPOINT unset — spans/metrics go to stdout.

Production:
    export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
"""
import os
import time
import logging
import threading

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Graceful import — module works fine without opentelemetry installed
# ---------------------------------------------------------------------------
try:
    from opentelemetry import trace, metrics
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import (
        PeriodicExportingMetricReader,
        ConsoleMetricExporter,
    )
    from opentelemetry.trace import ProxyTracerProvider

    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False
    _logger.info(
        "opentelemetry-sdk not installed — RG5329 telemetry disabled. "
        "Run: pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc"
    )

if _OTEL_AVAILABLE:
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        _OTLP_AVAILABLE = True
    except ImportError:
        _OTLP_AVAILABLE = False

# ---------------------------------------------------------------------------
# Lazy, thread-safe, idempotent initialization
# ---------------------------------------------------------------------------
_init_lock = threading.Lock()
_initialized = False
_tracer = None
_meter = None

# Business metric instruments
_perceptions_applied = None
_perceptions_skipped = None
_perception_base_amount = None
_processing_duration = None
_errors_counter = None
_taxes_restored = None
_cae_enrichments = None


def _setup_providers_if_needed():
    """
    Configure TracerProvider and MeterProvider only when no provider has been
    set yet (e.g. by opentelemetry-instrument auto-instrumentation).
    If auto-instrumentation is running we just reuse the global providers.
    """
    current = trace.get_tracer_provider()
    if not isinstance(current, ProxyTracerProvider):
        _logger.info(
            "RG5329 OTel: reusing existing TracerProvider (%s)",
            type(current).__name__,
        )
        return

    resource = Resource.create({
        "service.name": os.environ.get("OTEL_SERVICE_NAME", "odoo-rg5329"),
        "service.version": "18.0.1.0.0",
        "service.namespace": "odoo",
    })

    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")

    # --- Traces ---
    if otlp_endpoint and _OTLP_AVAILABLE:
        span_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        _logger.info("RG5329 OTel: traces → OTLP %s", otlp_endpoint)
    else:
        span_exporter = ConsoleSpanExporter()
        _logger.info(
            "RG5329 OTel: traces → stdout "
            "(set OTEL_EXPORTER_OTLP_ENDPOINT to send to a collector)"
        )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    # --- Metrics ---
    if otlp_endpoint and _OTLP_AVAILABLE:
        metric_exporter = OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True)
    else:
        metric_exporter = ConsoleMetricExporter()

    reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=30_000)
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(meter_provider)


def _init():
    """Initialize OTel instruments. Thread-safe, idempotent."""
    global _initialized, _tracer, _meter
    global _perceptions_applied, _perceptions_skipped, _perception_base_amount
    global _processing_duration, _errors_counter, _taxes_restored, _cae_enrichments

    if _initialized or not _OTEL_AVAILABLE:
        return

    with _init_lock:
        if _initialized:
            return  # double-checked locking

        _setup_providers_if_needed()

        _tracer = trace.get_tracer(
            "rg5329",
            schema_url="https://opentelemetry.io/schemas/1.11.0",
        )
        _meter = metrics.get_meter("rg5329", version="18.0.1.0.0")

        _perceptions_applied = _meter.create_counter(
            name="rg5329_perceptions_applied_total",
            description="Total RG5329 perception taxes applied across order lines",
            unit="1",
        )
        _perceptions_skipped = _meter.create_counter(
            name="rg5329_perceptions_skipped_total",
            description="Total times RG5329 perception was not applied (with reason)",
            unit="1",
        )
        _perception_base_amount = _meter.create_histogram(
            name="rg5329_perception_base_amount_ars",
            description="Base line subtotal (ARS) on which RG5329 perception was applied",
            unit="1",
        )
        _processing_duration = _meter.create_histogram(
            name="rg5329_apply_logic_duration_ms",
            description="Wall-clock duration of _apply_rg5329_logic() in milliseconds",
            unit="1",
        )
        _errors_counter = _meter.create_counter(
            name="rg5329_errors_total",
            description="Total unhandled errors in RG5329 processing methods",
            unit="1",
        )
        _taxes_restored = _meter.create_counter(
            name="rg5329_taxes_restored_total",
            description="Total RG5329 taxes restored after order confirmation (indicates tax loss during confirm)",
            unit="1",
        )
        _cae_enrichments = _meter.create_counter(
            name="rg5329_cae_enrichments_total",
            description="Total CAE requests enriched with CondicionIVAReceptorId (RG 5616)",
            unit="1",
        )

        _initialized = True
        _logger.info("RG5329 OTel: telemetry initialized")


# ---------------------------------------------------------------------------
# No-op fallback span — same interface as an OTel span
# ---------------------------------------------------------------------------
class _NoOpSpan:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def set_attribute(self, key, value):
        pass

    def record_exception(self, exc, attributes=None):
        pass

    def set_status(self, status, description=None):
        pass

    def add_event(self, name, attributes=None):
        pass


# ---------------------------------------------------------------------------
# Public helpers — safe to call even when OTel is not installed
# ---------------------------------------------------------------------------

def start_span(name: str):
    """
    Return a context manager that opens an OTel span (or a no-op).

    Usage::

        with otel.start_span("rg5329.sale.apply_logic") as span:
            span.set_attribute("order.name", self.name)
            ...
    """
    _init()
    if not _OTEL_AVAILABLE or _tracer is None:
        return _NoOpSpan()
    return _tracer.start_as_current_span(name)


def record_perception_applied(
    order_type: str = "sale",
    rate: float = 3.0,
    base_amount: float = 0.0,
):
    """
    Record that a RG5329 perception tax was applied to an order line.

    :param order_type: "sale" or "purchase"
    :param rate: perception rate used (3.0 or 1.5)
    :param base_amount: line.price_subtotal used as the perception base (ARS)
    """
    _init()
    attrs = {"order_type": order_type, "rate": str(rate)}
    if _perceptions_applied:
        _perceptions_applied.add(1, attrs)
    if _perception_base_amount and base_amount > 0:
        _perception_base_amount.record(base_amount, attrs)


def record_perception_skipped(order_type: str = "sale", reason: str = "unknown"):
    """
    Record that a RG5329 perception was NOT applied to an order line.

    Possible reasons:
        - ``customer_exempt``  — partner.rg5329_exempt is True
        - ``not_eligible``     — partner AFIP code != '1'
        - ``below_threshold``  — order total < $10,000,000 ARS
        - ``no_tax_found``     — RG5329 account.tax record missing in DB
        - ``wrong_state``      — order state not in ['draft', 'sent']
    """
    _init()
    if _perceptions_skipped:
        _perceptions_skipped.add(1, {"order_type": order_type, "reason": reason})


def record_error(method_name: str):
    """Record an unhandled exception in a RG5329 processing method."""
    _init()
    if _errors_counter:
        _errors_counter.add(1, {"method": method_name})


def record_processing_duration(duration_ms: float, order_type: str = "sale"):
    """Record wall-clock duration of a _apply_rg5329_logic() call."""
    _init()
    if _processing_duration:
        _processing_duration.record(duration_ms, {"order_type": order_type})


def record_taxes_restored(count: int, order_type: str = "purchase"):
    """
    Record that RG5329 taxes were restored after order confirmation.

    A non-zero count means the confirm flow stripped the taxes and the
    restore mechanism had to re-add them — useful to track how often
    this safety net fires.

    :param count: number of lines on which taxes were restored
    :param order_type: "purchase" (sale orders don't go through confirm)
    """
    _init()
    if _taxes_restored and count > 0:
        _taxes_restored.add(count, {"order_type": order_type})


def record_cae_enrichment(condicion_iva: int):
    """
    Record that a CAE WSFE request was enriched with CondicionIVAReceptorId
    as required by RG 5616.

    :param condicion_iva: the fiscal condition code injected into the request
    """
    _init()
    if _cae_enrichments:
        _cae_enrichments.add(1, {"condicion_iva": str(condicion_iva)})
