# Cambios realizados respecto al prototipo de celdas

## Conservado

- Inicio biológico desde entrada de aves.
- Asociación de consumo, mortalidad y producción por orden.
- Edad inicial parametrizada.
- Materiales y fases definidos en configuración.
- Separación entre stock global y consumo de ciclo.
- Fórmulas de política, ICA y brechas.
- Código legacy preservado en `legacy/prototipo_celdas`.

## Mejorado

1. Código dividido en módulos con responsabilidades únicas.
2. Configuración externa YAML.
3. Carga reproducible de fuentes.
4. Normalización centralizada de fechas, cantidades y llaves SAP.
5. Catálogo auditable de movimientos y roles.
6. Pipeline ejecutable desde CLI.
7. Pruebas unitarias.
8. Manifiesto de ejecución y logs.
9. Features de anomalía y baseline Isolation Forest.
10. Documentación organizada por fases.
11. Dashboard ejecutivo separado de la lógica de transformación.
12. Conservación explícita de movimientos desconocidos para revisión.
