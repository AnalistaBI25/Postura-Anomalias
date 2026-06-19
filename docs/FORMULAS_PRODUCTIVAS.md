# Fórmulas productivas

## Edad

La edad inicial se define en configuración:

```text
edad_total_días = initial_age_week * 7 + initial_age_day + días_desde_entrada
```

## Consumo esperado

```text
consumo_esperado_kg_día = aves_disponibles * consumo_g_ave_día / 1000
```

## Producción esperada

```text
producción_esperada_kg_día = aves_disponibles * porcentaje_producción * peso_huevo_g / 1000
```

## Mortalidad esperada

```text
mortalidad_estándar_acumulada = aves_iniciales * mortalidad_pct_acumulada / 100
```

## Consumo neto

```text
consumo_neto = consumo 261 WA - reversa 262 WA
```

## Producción neta

```text
producción_neta = producto principal neto + subproducto neto
```

## ICA semanal

```text
ICA_real = consumo_neto_semanal / producción_neta_semanal
```

Se utiliza el ICA oficial de la política cuando existe. El ICA calculado desde consumo y producción estándar funciona como respaldo y control de consistencia.
