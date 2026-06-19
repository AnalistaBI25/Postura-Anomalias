# Reglas de movimientos SAP del proyecto

Las reglas se parametrizan desde `config/project.yml`. Esta documentación describe roles y movimientos sin exponer materiales empresariales reales.

## Aves - material configurado como `bird_material`

| Movimiento | Evento | Interpretación |
|---|---|---|
| 101 | WE | Entrada de aves e inicio biológico |
| 102 | WE | Reversa de entrada |
| 261 | WR | Mortalidad |
| 262 | WR | Reversa de mortalidad |
| 261 | WA | Salida de parvada |
| 262 | WA | Reversa de salida |
| 641/642/643 | WL u operativo | Contexto logístico; no define consumo ni producción |
| 511/512/701/702 | WI u operativo | Contexto de ajuste; no modifica automáticamente el saldo biológico |

## Alimento - materiales configurados en `feed_materials`

| Movimiento | Evento | Interpretación |
|---|---|---|
| 101 | WE | Entrada al almacén de alimento |
| 102 | WE | Reversa de entrada |
| 261 | WA | Consumo por orden/ciclo |
| 262 | WA | Reversa de consumo |
| 301/311 | variable | Traspasos de inventario |
| 511/512 | WI o similar | Ajustes y reversas |
| 551/552 | variable | Mermas y reversas |
| 641/642/643 | WL u operativo | Logística o tránsito |
| 701/702 | WI | Diferencias positivas/negativas de inventario |

## Producción

- Producto principal: materiales configurados en `normal_egg_materials` con 101/102 WF.
- Subproductos: materiales configurados en `subproduct_materials` con 531/532 WA.
- Movimientos logísticos, ajustes y mermas se mantienen como contexto de inventario, no como producción nueva.

## Principio de diseño

La interpretación nunca depende solo del número de movimiento. Se utiliza:

`material + movimiento + evento + almacén + orden`

Las combinaciones no reconocidas permanecen como `NO_CLASIFICADO` y deben revisarse antes de incorporarse como regla definitiva.
