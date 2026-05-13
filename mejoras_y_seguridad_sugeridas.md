# Mejoras y Medidas de Seguridad Sugeridas (Sesiones Posteriores)

Este documento contiene un conjunto de recomendaciones clave orientadas tanto a perfeccionar la funcionalidad analítica de **SOVEREIGN AML** como a blindar la aplicación bajo los estándares de seguridad de **OWASP Top 10**.

---

## 1. Mejoras Funcionales y Analíticas Sugeridas

1. **Integración con Kaleido o Plotly Orca**: Actualmente, el entorno no tiene instalado `kaleido`, de manera que los PDFs se construyen renderizando gráficas con `matplotlib`. Para mantener un ecosistema totalmente homogéneo que coincida 1:1 con las vistas web de *Plotly*, se sugiere incorporar *kaleido* y configurar la exportación estática de Plotly en `mod_reportes.py`.
2. **Exportar Archivos a Excel (con Macros/Filtros Avanzados)**: Además de reportes PDF, permitir exportar las transacciones filtradas por Riesgo o Cliente directamente a un formato nativo XLSX formateado para auditores externos de la SIB.
3. **Módulo de Log de Auditoría Operativa**: Crear una vista interna donde se documente qué usuario ha generado qué reporte PDF, qué alertas modificaron umbrales técnicos y en qué fecha, para preservar una bitácora inmutable de eventos conforme a normativas internacionales.
4. **Almacenamiento Persistente Real**: La plataforma ya conserva el análisis cargado durante la sesión mediante caché temporal local y archivos `.saml`. Para colaboración multiusuario o historiales de largo plazo, migrar a una base de datos ligera como SQLite o PostgreSQL (mediante *SQLAlchemy*), preservando bitácoras por analista y fecha.

---

## 2. Aplicación de Estándares de Seguridad (OWASP Top 10)

Para blindar la plataforma dado que procesa datos financieros sumamente confidenciales, recomiendo implementar las siguientes remediaciones en próximas versiones:

* **A01:2021 – Broken Access Control (Control de Acceso)**: 
  * *Implementación Sugerida*: Implementar inicio de sesión mediante OAuth 2.0 (ej. Azure AD, Okta o Auth0) y establecer Roles Basados en Permisos (RBAC), limitando quién puede extraer KPIs o generar RTS. 
* **A02:2021 – Cryptographic Failures (Fallos Criptográficos)**: 
  * *Implementación Sugerida*: Evitar exponer archivos PDF generados mediante URL compartidas HTTP. Asegurarse de que el servidor local de Streamlit corra estrictamente bajo `HTTPS` en producción utilizando certificados SSL/TLS y cifrado de discos (AES-256) donde se almacenen las bases de datos de transacciones de los clientes.
* **A03:2021 – Injection (Inyección)**: 
  * *Implementación Sugerida*: Si en un futuro se migran las búsquedas de "Cliente" hacia bases de datos SQL en lugar de DataFrames de Pandas, se debe aplicar estricto tipado (`Prepared Statements` o uso transaccional via ORMs) garantizando que no existan vectores de `SQL Injection`.
* **A05:2021 – Security Misconfiguration (Configuración de Seguridad Deficiente)**:
  * *Implementación Sugerida*: Minimizar información revelada en errores por pantalla (`st.error("Traceback...")`). Se debe apagar el modo Debug de las trazas subyacentes e implementar manejadores de excepciones genéricos hacia la interfaz, persistiendo el error en un log oculto al usuario.
* **A07:2021 – Identification and Authentication Failures (Fallos de Autenticación)**:
  * *Estado actual*: Implementado cierre automático por 30 minutos de inactividad, limpieza de caché temporal al expirar/cerrar sesión y restauración segura ante recarga accidental mientras la sesión esté vigente.
  * *Mejora futura*: Para producción, integrar OAuth 2.0/OIDC, MFA y políticas corporativas de sesión centralizadas.
* **A08:2021 – Software and Data Integrity Failures (Integridad de Software y Datos)**:
  * *Estado actual*: Dependencias backend fijadas en `requirements.txt` y auditoría `pip-audit` ejecutada sin vulnerabilidades conocidas tras actualizar `GitPython`, `lxml`, `Pillow`, `pip` y `urllib3`.
  * *Mejora futura*: Implementar chequeos de integridad al subir el archivo Excel base y validar hashes/reproducibilidad en un pipeline CI/CD.

**Próximo Paso Inmediato para Producción**: Envolver el proyecto dentro de un contenedor en *Docker* completamente hermético que no comparta volúmenes de red innecesarios y ejecute procesos con un perfil de usuario no-root dentro del sistema (`USER appuser`).
