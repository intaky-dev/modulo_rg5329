# Modulo RG 5329 - Percepción IVA

Módulo para aplicar el régimen de percepción de IVA establecido por la RG 5329/2023 en Odoo 18.

## Características

- Percepción 3% para productos con IVA 21%
- Percepción 1,5% para productos con IVA 10,5%
- Configuración simple en productos para activar cálculo
- Mínimo de $100,000 en el total de compra
- Cálculo automático según alícuota de IVA
- Creación automática de cuenta contable 2.1.3.03.041
- Exención por cliente
- Tax group para visualización clara en facturas

## Instalación

### Automática (Recomendada)

Ejecute el script de instalación automática:

```bash
./auto_install_simple_final.sh
```

Este script:
1. Copia el módulo al contenedor Odoo en `odoo-enter18`
2. Instala automáticamente el módulo via API
3. Crea datos de demostración

### Manual

1. Asegúrese de que Odoo esté ejecutándose desde `odoo-enter18`
2. Copie este directorio completo al contenedor
3. Vaya a Apps → Update Apps List
4. Busque "RG 5329" e instale

## Uso

1. **Productos**: Marque "Aplicar RG 5329" en productos sujetos a percepción
2. **Clientes**: Marque "Exento RG 5329" para clientes exentos
3. **Facturas**: El cálculo se aplica automáticamente cuando se cumplen las condiciones