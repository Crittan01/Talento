/* ============================================================================
   renderers.js — Renderers especializados por tipo de resultado.
   Cada uno recibe el dict de artifacts (set_stats del playbook) y devuelve
   HTML que se inyecta en el panel derecho.
   ============================================================================ */

const Renderers = {

  // --- helpers compartidos ---
  _kpi(label, value) {
    return `<div class="ecp-kpi">
              <div class="ecp-kpi__value">${value ?? '—'}</div>
              <div class="ecp-kpi__label">${label}</div>
            </div>`;
  },

  _severityBadge(status, mapping) {
    const cls = mapping[status] || 'severity-neutral';
    return `<span class="severity-badge ${cls}">${status || 'N/A'}</span>`;
  },

  _table(headers, rows, maxRows = 10) {
    if (!rows || rows.length === 0) {
      return '<p style="color: var(--text-muted); font-style: italic;">Sin datos.</p>';
    }
    const limited = rows.slice(0, maxRows);
    const head = headers.map(h => `<th>${h}</th>`).join('');
    const body = limited.map(r =>
      '<tr>' + r.map(c => `<td>${this._escapeHtml(String(c ?? ''))}</td>`).join('') + '</tr>'
    ).join('');
    return `<table class="ecp-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  },

  _escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  },

  _actions(awxUrl) {
    if (!awxUrl) return '';
    return `<div class="ecp-actions">
              <a href="${awxUrl}" target="_blank" class="ecp-btn">Ver job en AWX ↗</a>
              <button class="ecp-btn ecp-btn--secondary" onclick="window.scrollTo({top:0,behavior:'smooth'})">Volver arriba</button>
            </div>`;
  },

  // --- snapshot (JT 48) ---
  snapshot(a, awxUrl) {
    const tablesRows = a.all_tables_summary || [];
    return `
      <h4 style="margin-top:0;">📊 Estado del Workspace</h4>
      <div class="ecp-kpi-grid">
        ${this._kpi('Tablas con datos', a.n_tables_with_data)}
        ${this._kpi('Top tabla', this._escapeHtml(String(a.top_table_name || '—')))}
        ${this._kpi('Filas en top tabla', a.top_table_rows)}
        ${this._kpi('Rango (h)', a.time_range_hours)}
      </div>
      <h5>Tablas pobladas (descendente):</h5>
      ${this._table(['Tabla', 'Registros'], tablesRows)}
      ${this._actions(awxUrl)}
    `;
  },

  // --- errors (JT 49) ---
  errors(a, awxUrl) {
    const sevMap = {
      'CRITICAL': 'severity-critical',
      'WARN': 'severity-warn',
      'OK': 'severity-good',
    };
    return `
      <h4 style="margin-top:0;">🚨 Análisis de Errores & Warnings</h4>
      <p>Estado: ${this._severityBadge(a.severity_status, sevMap)}</p>
      <div class="ecp-kpi-grid">
        ${this._kpi('Errores', a.total_errors)}
        ${this._kpi('Warnings', a.total_warnings)}
        ${this._kpi('Containers afectados', (a.affected_containers || []).length)}
        ${this._kpi('Rango (h)', a.time_range_hours)}
      </div>
      <h5>Top 5 mensajes recurrentes:</h5>
      ${this._table(['Mensaje (snippet)', 'Conteo'], (a.top_messages || []).map(r => [r[0], r[1]]))}
      <h5>Containers afectados:</h5>
      ${this._table(['Container', 'Eventos'], a.affected_containers || [])}
      ${this._actions(awxUrl)}
    `;
  },

  // --- SOX audit (JT 50) ---
  sox(a, awxUrl) {
    const sevMap = {
      'SECURITY_INCIDENT': 'severity-critical',
      'AUDIT_REVIEW': 'severity-warn',
      'NORMAL': 'severity-good',
    };
    return `
      <h4 style="margin-top:0;">🔐 Auditoría SOX — TALENTO</h4>
      <p>Estado: ${this._severityBadge(a.audit_status, sevMap)}</p>
      <div class="ecp-kpi-grid">
        ${this._kpi('Eventos de login', a.total_login_events)}
        ${this._kpi('Usuarios únicos', a.unique_users)}
        ${this._kpi('Acciones privilegiadas', a.total_privileged_actions)}
        ${this._kpi('Incidentes seguridad BD', a.total_security_incidents)}
      </div>
      <h5>Actividad de login por usuario:</h5>
      ${this._table(['Usuario', 'Tipo', 'Eventos'], a.login_breakdown || [])}
      <h5>Acciones privilegiadas:</h5>
      ${this._table(['Acción', 'Rol', 'Conteo'], a.privileged_breakdown || [])}
      <h5>Incidentes de seguridad BD (top):</h5>
      ${this._table(['Mensaje', 'Ocurrencias'], (a.security_incidents || []).map(r => [r[0], r[1]]))}
      ${this._actions(awxUrl)}
    `;
  },

  // --- Brute force (JT 51, formato similar a SOX) ---
  'brute-force'(a, awxUrl) {
    const sevMap = {
      'HIGH': 'severity-critical',
      'MEDIUM': 'severity-warn',
      'LOW': 'severity-good',
    };
    return `
      <h4 style="margin-top:0;">🛡️ Detección de Brute Force</h4>
      <p>Severidad: ${this._severityBadge(a.bruteforce_severity || 'LOW', sevMap)}</p>
      <div class="ecp-kpi-grid">
        ${this._kpi('Usuarios sospechosos', a.suspicious_users_count ?? 0)}
        ${this._kpi('Failed logins totales', a.total_failed_logins ?? 0)}
        ${this._kpi('Umbral configurado', a.failed_threshold)}
        ${this._kpi('Rango (h)', a.time_range_hours)}
      </div>
      <h5>Usuarios con intentos fallidos:</h5>
      ${this._table(['Usuario', 'Intentos fallidos'], a.suspicious_users || [])}
      <h5>Top mensajes detectados:</h5>
      ${this._table(['Mensaje (snippet)', 'Conteo'], (a.top_messages || []).map(r => [r[0], r[1]]))}
      ${this._actions(awxUrl)}
    `;
  },

  // --- Generic / Pregunta libre ---
  generic(a, awxUrl) {
    if (!a || Object.keys(a).length === 0) {
      return `<p style="color: var(--text-muted);">Sin artifacts estructurados — revisa el texto sintetizado por el agente.</p>${this._actions(awxUrl)}`;
    }
    const rows = Object.entries(a).map(([k, v]) => [
      k,
      typeof v === 'object' ? JSON.stringify(v).slice(0, 200) : String(v).slice(0, 200)
    ]);
    return `
      <h4 style="margin-top:0;">🤖 Resultado</h4>
      ${this._table(['Campo', 'Valor'], rows, 30)}
      ${this._actions(awxUrl)}
    `;
  },
};
