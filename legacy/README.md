# Respaldos y componentes históricos

Esta carpeta contiene material preservado que ya no forma parte de la operación
activa del pipeline.

```text
legacy/
├── chencopo_pre_multigranja/  datos y resultados anteriores a farm_id
├── prototipo_celdas/          código histórico del prototipo
└── tooling/                   evidencia local de herramientas de análisis
```

- `chencopo_pre_multigranja/` es el respaldo recuperable de las antiguas
  carpetas `data`, `models`, `reports`, `outputs` y `logs`.
- `prototipo_celdas/` conserva las últimas versiones disponibles de las celdas
  6, 6A y 7 para comparación histórica.
- `tooling/` almacena resultados de herramientas que no son necesarios para
  ejecutar el proyecto.

La operación vigente de Chencopo está en `farms/chencopo_2/`. No se debe leer
este directorio desde el pipeline productivo.
