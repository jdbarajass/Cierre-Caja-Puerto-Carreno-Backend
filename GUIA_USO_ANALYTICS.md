# Guía de Uso - Analytics API

## 🚀 Inicio Rápido

### 1. Iniciar el Servidor

```bash
python run.py
```

El servidor iniciará en `http://localhost:5000`

### 2. Obtener Token de Autenticación

```bash
curl -X POST http://localhost:5000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "tu_usuario", "password": "tu_contraseña"}'
```

**Respuesta:**
```json
{
  "success": true,
  "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "user": {
    "id": "1",
    "username": "admin"
  }
}
```

Copia el token para usarlo en las siguientes peticiones.

---

## 📊 Ejemplos de Uso por Funcionalidad

### 1️⃣ Horas Pico de Ventas

**Objetivo:** Identificar las mejores horas para programar personal

**Consulta del mes actual:**
```bash
curl -X GET "http://localhost:5000/api/analytics/peak-hours?start_date=2025-11-01&end_date=2025-11-30" \
  -H "Authorization: Bearer TU_TOKEN_AQUI"
```

**¿Qué obtendrás?**
- Top 5 horas con más ventas
- Desglose de 24 horas completo
- Ventas por hora para cada día de la semana

**Aplicación práctica:**
- Si el top 1 es 19:00-20:00, programa más personal a esa hora
- Si Lunes a las 14:00 tiene baja actividad, reduce personal

---

### 2️⃣ Top Clientes

**Objetivo:** Identificar clientes VIP para programas de fidelización

**Consulta top 10 clientes del mes:**
```bash
curl -X GET "http://localhost:5000/api/analytics/top-customers?start_date=2025-11-01&end_date=2025-11-30&limit=10" \
  -H "Authorization: Bearer TU_TOKEN_AQUI"
```

**¿Qué obtendrás?**
- Top clientes por gasto total
- Frecuencia de compra de cada uno
- Ticket promedio
- Método de pago favorito

**Aplicación práctica:**
- Cliente con 10+ compras → Enviar tarjeta de fidelización
- Cliente que gasta $500k+ → Invitar a evento VIP
- Cliente que no compra hace 60 días → Campaña de reactivación

---

### 3️⃣ Top Vendedoras

**Objetivo:** Evaluar desempeño y dar bonificaciones

**Consulta del mes:**
```bash
curl -X GET "http://localhost:5000/api/analytics/top-sellers?start_date=2025-11-01&end_date=2025-11-30" \
  -H "Authorization: Bearer TU_TOKEN_AQUI"
```

**¿Qué obtendrás?**
- Ranking de vendedoras por ingresos
- Número de facturas
- Ticket promedio
- Hora más productiva

**Aplicación práctica:**
- Vendedora #1 → Bono de desempeño
- Vendedora con ticket alto → Compartir técnicas de venta
- Hora productiva 19:00 → Programarla en ese horario

---

### 4️⃣ Retención de Clientes

**Objetivo:** Prevenir abandono y fomentar lealtad

**Consulta de últimos 60 días:**
```bash
curl -X GET "http://localhost:5000/api/analytics/customer-retention?start_date=2025-10-01&end_date=2025-11-30" \
  -H "Authorization: Bearer TU_TOKEN_AQUI"
```

**¿Qué obtendrás?**
- Segmentación: Nuevos / Recurrentes / Leales
- Clientes activos vs en riesgo vs inactivos
- Top clientes leales
- Clientes en riesgo de abandono

**Aplicación práctica:**
- Cliente "En riesgo" (no compra hace 100 días) → Email de descuento
- Cliente "Leal" (7+ compras) → Programa VIP
- Tasa de retención baja (< 30%) → Mejorar experiencia

---

### 5️⃣ Tendencias de Ventas

**Objetivo:** Planificar inventario y proyectar ventas

**Consulta de últimas 2 semanas:**
```bash
curl -X GET "http://localhost:5000/api/analytics/sales-trends?start_date=2025-11-15&end_date=2025-11-30" \
  -H "Authorization: Bearer TU_TOKEN_AQUI"
```

**¿Qué obtendrás?**
- Ventas día por día
- Mejor y peor día
- Análisis por día de la semana
- Promedio diario

**Aplicación práctica:**
- Sábados venden $500k promedio → Pedir más inventario viernes
- Lunes venden poco → Programar mantenimiento ese día
- Tendencia a la baja → Lanzar promoción

---

### 6️⃣ Cross-Selling

**Objetivo:** Crear combos y aumentar ticket promedio

**Consulta del mes:**
```bash
curl -X GET "http://localhost:5000/api/analytics/cross-selling?start_date=2025-11-01&end_date=2025-11-30&min_support=3" \
  -H "Authorization: Bearer TU_TOKEN_AQUI"
```

**¿Qué obtendrás?**
- Pares de productos que se compran juntos
- Frecuencia de compra conjunta
- Confianza (probabilidad)

**Aplicación práctica:**
- Jean + Camiseta (comprados juntos 15 veces) → Crear combo con descuento
- Si compran Jean (45% de prob.) → Vendedora ofrece camiseta
- Ubicar productos juntos en tienda

---

### 7️⃣ Dashboard Completo

**Objetivo:** Vista unificada de todos los KPIs

**Consulta semanal:**
```bash
curl -X GET "http://localhost:5000/api/analytics/dashboard?start_date=2025-11-22&end_date=2025-11-28" \
  -H "Authorization: Bearer TU_TOKEN_AQUI"
```

**¿Qué obtendrás?**
- TODOS los análisis en una sola petición
- Ideal para dashboards ejecutivos

---

## 💼 Casos de Uso Empresariales

### Caso 1: Optimización de Personal
**Problema:** No sabemos cuándo programar más personal

**Solución:**
1. Consultar `/api/analytics/peak-hours` del último mes
2. Identificar top 3 horas con más ventas
3. Programar 2 vendedoras en esas horas
4. Reducir personal en horas de baja demanda

**Resultado:** -20% en costos de nómina, +15% satisfacción del cliente

---

### Caso 2: Programa de Fidelización
**Problema:** Queremos crear un programa VIP pero no sabemos a quién invitar

**Solución:**
1. Consultar `/api/analytics/top-customers` de últimos 3 meses
2. Filtrar clientes con:
   - Gasto total > $500.000
   - Frecuencia > 5 compras
3. Enviar invitación a programa VIP

**Resultado:** +25% de ventas de clientes VIP

---

### Caso 3: Reactivación de Clientes
**Problema:** Muchos clientes no vuelven después de primera compra

**Solución:**
1. Consultar `/api/analytics/customer-retention` mensual
2. Identificar clientes "En riesgo" (90-180 días sin compra)
3. Enviar email con descuento 20% personalizado
4. Llamada de seguimiento

**Resultado:** +30% de reactivación

---

### Caso 4: Incremento de Ticket Promedio
**Problema:** Ticket promedio es bajo ($35.000)

**Solución:**
1. Consultar `/api/analytics/cross-selling` último mes
2. Identificar top 5 combos más vendidos
3. Capacitar vendedoras para ofrecer esos combos
4. Crear promoción "Lleva 2 productos y ahorra 10%"

**Resultado:** Ticket promedio aumenta a $45.000

---

### Caso 5: Evaluación de Desempeño
**Problema:** No tenemos datos objetivos para bonos

**Solución:**
1. Consultar `/api/analytics/top-sellers` mensual
2. Establecer KPIs:
   - Top 1: Bono $200.000
   - Top 2: Bono $150.000
   - Top 3: Bono $100.000
3. Compartir mejores prácticas de vendedora #1

**Resultado:** +40% motivación del equipo, +20% en ventas

---

## 🎯 Flujos Recomendados

### Flujo Diario (5 minutos)
```bash
# Ver ventas de ayer
GET /api/analytics/sales-trends?date=2025-11-28

# Ver top vendedora de ayer
GET /api/analytics/top-sellers?date=2025-11-28&limit=3
```

### Flujo Semanal (15 minutos)
```bash
# Dashboard completo de la semana
GET /api/analytics/dashboard?start_date=2025-11-22&end_date=2025-11-28

# Identificar clientes en riesgo
GET /api/analytics/customer-retention?start_date=2025-10-01&end_date=2025-11-28
```

### Flujo Mensual (30 minutos)
```bash
# Todas las métricas del mes
GET /api/analytics/dashboard?start_date=2025-11-01&end_date=2025-11-30

# Top 20 clientes
GET /api/analytics/top-customers?start_date=2025-11-01&end_date=2025-11-30&limit=20

# Análisis de cross-selling para nuevos combos
GET /api/analytics/cross-selling?start_date=2025-11-01&end_date=2025-11-30&min_support=5
```

---

## 🧪 Probar con el Script de Prueba

Incluimos un script Python para probar todos los endpoints:

```bash
# Editar el archivo test_analytics_endpoints.py
# Actualizar usuario y contraseña en la función test_login()

# Ejecutar
python test_analytics_endpoints.py
```

El script probará automáticamente:
- ✅ Autenticación
- ✅ Horas pico
- ✅ Top clientes
- ✅ Top vendedoras
- ✅ Retención
- ✅ Tendencias
- ✅ Cross-selling
- ✅ Dashboard

---

## 📱 Integración con Frontend

### Con React/Vue/Angular

```javascript
// Configurar axios
import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:5000',
  headers: {
    'Authorization': `Bearer ${localStorage.getItem('token')}`
  }
});

// Obtener horas pico
const getPeakHours = async (startDate, endDate) => {
  const response = await api.get('/api/analytics/peak-hours', {
    params: { start_date: startDate, end_date: endDate }
  });
  return response.data;
};

// Obtener top clientes
const getTopCustomers = async (limit = 10) => {
  const response = await api.get('/api/analytics/top-customers', {
    params: { limit, start_date: '2025-11-01', end_date: '2025-11-30' }
  });
  return response.data;
};

// Uso
const loadDashboard = async () => {
  const peakHours = await getPeakHours('2025-11-01', '2025-11-30');
  const topCustomers = await getTopCustomers(10);

  console.log('Mejor hora:', peakHours.data.top_5_peak_hours[0]);
  console.log('Mejor cliente:', topCustomers.data.top_customers[0]);
};
```

---

## 🔍 Troubleshooting

### Error 401 (Unauthorized)
**Problema:** Token inválido o expirado

**Solución:**
```bash
# Obtener nuevo token
curl -X POST http://localhost:5000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "password"}'
```

### Error 502 (Bad Gateway)
**Problema:** No se puede conectar con Alegra

**Solución:**
- Verificar credenciales en `.env`
- Verificar conexión a internet
- Verificar que API de Alegra esté funcionando

### Sin datos en respuesta
**Problema:** No hay facturas en el rango de fechas

**Solución:**
- Verificar que haya ventas en ese período
- Usar un rango de fechas más amplio
- Verificar en Alegra que las facturas existan

---

## 📊 Visualización Recomendada

### Para Horas Pico
- **Gráfico:** Barras por hora
- **Colores:** Verde (alto), Amarillo (medio), Rojo (bajo)

### Para Top Clientes
- **Gráfico:** Tabla ordenada + gráfico de torta
- **Destacar:** Top 3 con badges

### Para Tendencias
- **Gráfico:** Línea temporal
- **Marcadores:** Mejor y peor día

### Para Cross-Selling
- **Gráfico:** Red de conexiones
- **Tamaño:** Proporcional a frecuencia

---

## 🎓 Capacitación del Equipo

### Para Vendedoras:
1. Mostrar su desempeño individual
2. Comparar con promedio
3. Identificar oportunidades de mejora

### Para Gerencia:
1. Dashboard mensual completo
2. KPIs principales
3. Recomendaciones basadas en datos

### Para Marketing:
1. Segmentación de clientes
2. Productos que se venden juntos
3. Clientes para campañas

---

## 📞 Soporte

¿Necesitas ayuda? Contacta al equipo de desarrollo.

---

**Última actualización:** Noviembre 2025
