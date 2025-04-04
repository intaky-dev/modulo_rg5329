# Módulo Odoo: rg5329_klap

## 📌 Descripción

Este módulo implementa la percepción impositiva RG 5329 dispuesta por la AFIP en Argentina, con el objetivo de aplicar automáticamente un **3% adicional** sobre ciertos productos alcanzados, **solo en casos en los que la suma total de esos productos en una factura supere los $100.000 ARS (sin impuestos)**.

## ¿Qué hace este módulo?

- Crea un nuevo grupo de impuestos y un nuevo impuesto "Percepción RG 5329 - PAIS 3%"
- Permite marcar productos que están sujetos a esta percepción
- Aplica automáticamente el impuesto solo si la suma total de los productos marcados supera los $100.000

## Uso

1. Tildar la opción "Aplicar Percepción RG 5329" en los productos deseados.
2. Al crear una factura de cliente, si la suma de estos productos supera los 100.000 ARS, el impuesto se aplicará automáticamente.

## Licencia

LGPL-3 – 2025 – FwCorp
