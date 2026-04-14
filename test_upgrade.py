#!/usr/bin/env python3
"""
Tests post-upgrade para modulo_rg5329
Valida los cambios del último deploy via XML-RPC.

Uso:
    python3 test_upgrade.py
    python3 test_upgrade.py --host http://mi-servidor:8069 --db odoo
    python3 test_upgrade.py --host http://mi-servidor:8069 --db odoo --password secret
"""
import xmlrpc.client
import sys
import argparse
from typing import Any


MODULE_NAME = "modulo_rg5329"
MODULE_VERSION = "18.0.1.0.0"


class OdooClient:
    def __init__(self, host: str, db: str, user: str, password: str):
        self.db = db
        self.password = password
        common = xmlrpc.client.ServerProxy(f"{host}/xmlrpc/2/common")
        self.uid = common.authenticate(db, user, password, {})
        if not self.uid:
            raise ConnectionError(f"Autenticacion fallida para {user}@{db}")
        self.models = xmlrpc.client.ServerProxy(f"{host}/xmlrpc/2/object")

    def execute(self, model: str, method: str, *args, **kwargs) -> Any:
        return self.models.execute_kw(
            self.db, self.uid, self.password, model, method, list(args), kwargs
        )


class Results:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors: list[str] = []

    def ok(self, name: str):
        self.passed += 1
        print(f"    [OK]   {name}")

    def fail(self, name: str, reason: str):
        self.failed += 1
        self.errors.append(f"{name}: {reason}")
        print(f"    [FAIL] {name}")
        print(f"           → {reason}")


def _test_purchase_threshold(client: OdooClient, r: Results) -> None:
    """Crea una PO de prueba y verifica el umbral $10M en compras."""
    partner_ids = client.execute(
        "res.partner", "search",
        [[["l10n_ar_afip_responsibility_type_id.code", "=", "1"],
          ["rg5329_exempt", "=", False]]],
        limit=1
    )
    if not partner_ids:
        r.fail("umbral PO - partner", "No hay partners RI no exentos para probar")
        return

    product_ids = client.execute(
        "product.product", "search",
        [[["apply_rg5329", "=", True]]],
        limit=1
    )
    if not product_ids:
        r.fail("umbral PO - product", "No hay productos con apply_rg5329=True para probar")
        return

    tax_ids = client.execute(
        "account.tax", "search",
        [[["is_rg5329_perception", "=", True],
          ["amount", "=", 3.0],
          ["type_tax_use", "=", "purchase"]]],
        limit=1
    )
    if not tax_ids:
        r.fail("umbral PO - tax", "No se encontró impuesto RG5329 de compras (3%)")
        return

    rg5329_tax_id = tax_ids[0]
    po_id = None

    try:
        # --- Crear PO con total bien por debajo del umbral ---
        po_id = client.execute("purchase.order", "create", {
            "partner_id": partner_ids[0],
            "order_line": [(0, 0, {
                "product_id": product_ids[0],
                "product_qty": 1,
                "price_unit": 500_000,      # $500k — bajo el umbral de $10M
                "name": "[TEST] RG5329 threshold check",
            })],
        })
        client.execute("purchase.order", "apply_rg5329_logic_manual", [po_id])

        lines = client.execute(
            "purchase.order.line", "search_read",
            [[["order_id", "=", po_id]]],
            fields=["id", "taxes_id"]
        )
        if not any(rg5329_tax_id in ln["taxes_id"] for ln in lines):
            r.ok("PO $500k < $10M → sin percepción RG5329")
        else:
            r.fail("umbral PO (bajo)", "Percepción aplicada con total < $10M — ¿umbral viejo $100k activo?")

        # --- Subir precio a exactamente el umbral ---
        line_ids = [ln["id"] for ln in lines]
        client.execute("purchase.order.line", "write", line_ids, {
            "price_unit": 10_000_000,       # $10M — en el umbral
        })
        client.execute("purchase.order", "apply_rg5329_logic_manual", [po_id])

        lines = client.execute(
            "purchase.order.line", "search_read",
            [[["order_id", "=", po_id]]],
            fields=["taxes_id"]
        )
        if any(rg5329_tax_id in ln["taxes_id"] for ln in lines):
            r.ok("PO $10M >= $10M → percepción RG5329 aplicada")
        else:
            r.fail("umbral PO (alto)", "Percepción NO aplicada con total >= $10M")

    except Exception as e:
        r.fail("umbral PO (ejecución)", str(e))
    finally:
        if po_id:
            try:
                client.execute("purchase.order", "button_cancel", [po_id])
            except Exception:
                pass
            try:
                client.execute("purchase.order", "unlink", [po_id])
            except Exception:
                pass


def _test_sale_threshold(client: OdooClient, r: Results) -> None:
    """Crea una SO de prueba y verifica el umbral $10M en ventas."""
    partner_ids = client.execute(
        "res.partner", "search",
        [[["l10n_ar_afip_responsibility_type_id.code", "=", "1"],
          ["rg5329_exempt", "=", False]]],
        limit=1
    )
    if not partner_ids:
        r.fail("umbral SO - partner", "No hay partners RI no exentos para probar")
        return

    product_ids = client.execute(
        "product.product", "search",
        [[["apply_rg5329", "=", True]]],
        limit=1
    )
    if not product_ids:
        r.fail("umbral SO - product", "No hay productos con apply_rg5329=True para probar")
        return

    tax_ids = client.execute(
        "account.tax", "search",
        [[["is_rg5329_perception", "=", True],
          ["amount", "=", 3.0],
          ["type_tax_use", "=", "sale"]]],
        limit=1
    )
    if not tax_ids:
        r.fail("umbral SO - tax", "No se encontró impuesto RG5329 de ventas (3%)")
        return

    rg5329_tax_id = tax_ids[0]
    so_id = None

    try:
        # --- Crear SO con total bien por debajo del umbral ---
        so_id = client.execute("sale.order", "create", {
            "partner_id": partner_ids[0],
            "order_line": [(0, 0, {
                "product_id": product_ids[0],
                "product_uom_qty": 1,
                "price_unit": 500_000,
                "name": "[TEST] RG5329 threshold check",
            })],
        })
        client.execute("sale.order", "apply_rg5329_logic_manual", [so_id])

        lines = client.execute(
            "sale.order.line", "search_read",
            [[["order_id", "=", so_id]]],
            fields=["id", "tax_id"]
        )
        if not any(rg5329_tax_id in ln["tax_id"] for ln in lines):
            r.ok("SO $500k < $10M → sin percepción RG5329")
        else:
            r.fail("umbral SO (bajo)", "Percepción aplicada con total < $10M — ¿umbral viejo $100k activo?")

        # --- Subir precio a exactamente el umbral ---
        line_ids = [ln["id"] for ln in lines]
        client.execute("sale.order.line", "write", line_ids, {
            "price_unit": 10_000_000,
        })
        client.execute("sale.order", "apply_rg5329_logic_manual", [so_id])

        lines = client.execute(
            "sale.order.line", "search_read",
            [[["order_id", "=", so_id]]],
            fields=["tax_id"]
        )
        if any(rg5329_tax_id in ln["tax_id"] for ln in lines):
            r.ok("SO $10M >= $10M → percepción RG5329 aplicada")
        else:
            r.fail("umbral SO (alto)", "Percepción NO aplicada con total >= $10M")

    except Exception as e:
        r.fail("umbral SO (ejecución)", str(e))
    finally:
        if so_id:
            try:
                client.execute("sale.order", "action_cancel", [so_id])
            except Exception:
                pass
            try:
                client.execute("sale.order", "unlink", [so_id])
            except Exception:
                pass


def run_tests(client: OdooClient) -> Results:
    r = Results()

    # ------------------------------------------------------------------
    # TEST 1: Módulo instalado con la versión correcta
    # ------------------------------------------------------------------
    print("\n[1] Estado del módulo")
    module_ids = client.execute(
        "ir.module.module", "search", [["name", "=", MODULE_NAME]]
    )
    if not module_ids:
        r.fail("módulo existe", f"'{MODULE_NAME}' no encontrado")
    else:
        info = client.execute(
            "ir.module.module", "read", module_ids[0],
            fields=["state", "installed_version"]
        )[0]
        if info["state"] == "installed":
            r.ok("módulo instalado (state=installed)")
        else:
            r.fail("módulo instalado", f"state={info['state']}")
        if info["installed_version"] == MODULE_VERSION:
            r.ok(f"versión correcta ({MODULE_VERSION})")
        else:
            r.fail(
                "versión",
                f"esperada={MODULE_VERSION}, actual={info['installed_version']}"
            )

    # ------------------------------------------------------------------
    # TEST 2: Tax group con l10n_ar_tribute_afip_code = '06'
    #         (movido a noupdate="0" para que se actualice en upgrades)
    # ------------------------------------------------------------------
    print("\n[2] Tax group 'Percepción RG 5329' (noupdate=0)")
    try:
        group_ids = client.execute(
            "account.tax.group", "search",
            [["name", "=", "Percepción RG 5329"]]
        )
        if not group_ids:
            r.fail("tax group existe", "No se encontró 'Percepción RG 5329'")
        else:
            g = client.execute(
                "account.tax.group", "read", group_ids[0],
                fields=["name", "l10n_ar_tribute_afip_code", "sequence"]
            )[0]
            afip_code = g.get("l10n_ar_tribute_afip_code")
            if afip_code == "06":
                r.ok("l10n_ar_tribute_afip_code = '06'")
            else:
                r.fail(
                    "l10n_ar_tribute_afip_code",
                    f"esperado='06', actual='{afip_code}' "
                    f"(el campo no se actualizó — verificar que noupdate='0' se deployó)"
                )
            if g.get("sequence") == 20:
                r.ok("sequence = 20")
            else:
                r.fail("sequence", f"esperado=20, actual={g.get('sequence')}")
    except Exception as e:
        r.fail(
            "tax group (l10n_ar_tribute_afip_code)",
            f"campo no accesible — posiblemente l10n_ar no tiene el campo: {e}"
        )

    # ------------------------------------------------------------------
    # TEST 3: Impuestos de percepción RG 5329 existen con alícuotas correctas
    # ------------------------------------------------------------------
    print("\n[3] Impuestos de percepción")
    for tax_name, expected_amount in [
        ("Percepción IVA RG 5329 - 3%", 3.0),
        ("Percepción IVA RG 5329 - 1.5%", 1.5),
    ]:
        tax_ids = client.execute(
            "account.tax", "search", [["name", "=", tax_name]]
        )
        if tax_ids:
            tax = client.execute(
                "account.tax", "read", tax_ids[0],
                fields=["name", "amount"]
            )[0]
            if abs(tax["amount"] - expected_amount) < 0.01:
                r.ok(f"{tax_name} (amount={expected_amount}%)")
            else:
                r.fail(
                    tax_name,
                    f"amount esperado={expected_amount}, actual={tax['amount']}"
                )
        else:
            r.fail(tax_name, "no encontrado")

    # ------------------------------------------------------------------
    # TEST 4: Cuenta contable 2.1.3.03.041
    # ------------------------------------------------------------------
    print("\n[4] Cuenta contable percepciones")
    account_ids = client.execute(
        "account.account", "search",
        [["code", "=", "2.1.3.03.041"]]
    )
    if account_ids:
        r.ok("cuenta 2.1.3.03.041 existe")
    else:
        r.fail(
            "cuenta 2.1.3.03.041",
            "no encontrada — puede ser normal si la empresa fue creada sin el módulo activo"
        )

    # ------------------------------------------------------------------
    # TEST 5: Campos custom del módulo accesibles en sus modelos
    # ------------------------------------------------------------------
    print("\n[5] Campos custom del módulo")
    custom_fields = [
        ("res.partner", "rg5329_exempt", False),
        ("product.template", "apply_rg5329", False),
    ]
    for model, field, value in custom_fields:
        try:
            client.execute(model, "search", [[field, "=", value]], limit=1)
            r.ok(f"{model}.{field} accesible")
        except Exception as e:
            r.fail(f"{model}.{field}", str(e))

    # ------------------------------------------------------------------
    # TEST 7: Umbral de percepción en purchase.order ($10M)
    # ------------------------------------------------------------------
    print("\n[7] Umbral $10M en purchase.order")
    _test_purchase_threshold(client, r)

    # ------------------------------------------------------------------
    # TEST 8: Umbral de percepción en sale.order ($10M)
    # ------------------------------------------------------------------
    print("\n[8] Umbral $10M en sale.order")
    _test_sale_threshold(client, r)

    # ------------------------------------------------------------------
    # TEST 9: account.move carga sin errores de import
    #         Valida indirectamente que wsfe_get_cae_request no tiene
    #         errores de sintaxis o imports faltantes.
    # ------------------------------------------------------------------
    print("\n[9] account.move (override wsfe_get_cae_request)")
    try:
        fields = client.execute(
            "account.move", "fields_get", [],
            attributes=["string", "type"]
        )
        # Si el modelo cargó, no hay errores de import en account_move.py
        if "name" in fields and "move_type" in fields:
            r.ok("account.move carga correctamente (sin errores de import)")
        else:
            r.fail("account.move fields_get", "respuesta inesperada del servidor")
    except Exception as e:
        r.fail(
            "account.move",
            f"error al acceder al modelo — puede indicar error en account_move.py: {e}"
        )

    return r


def main():
    parser = argparse.ArgumentParser(
        description=f"Tests post-upgrade {MODULE_NAME}"
    )
    parser.add_argument("--host",     default="http://localhost:8069")
    parser.add_argument("--db",       default="odoo")
    parser.add_argument("--user",     default="admin")
    parser.add_argument("--password", default="admin")
    args = parser.parse_args()

    print(f"Conectando a {args.host}  DB={args.db}  user={args.user}")
    try:
        client = OdooClient(args.host, args.db, args.user, args.password)
        print("Autenticacion OK")
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    results = run_tests(client)

    total = results.passed + results.failed
    print(f"\n{'=' * 52}")
    print(f"  RESULTADO: {results.passed}/{total} tests OK", end="")
    if results.failed:
        print(f"  ({results.failed} FALLARON)")
        print()
        for err in results.errors:
            print(f"  - {err}")
    else:
        print("  ✓ Todo OK")
    print("=" * 52)

    sys.exit(0 if results.failed == 0 else 1)


if __name__ == "__main__":
    main()
