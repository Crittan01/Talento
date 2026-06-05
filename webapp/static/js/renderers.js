/* ============================================================================
   renderers.js v21 — Renderers por tipo de resultado.
   - generic: fallback para todos los escenarios basados en síntesis del agente
   - health: System Health con veredicto por capa (lookup_infrastructure + lookup_sql)
   - errors / sox / brute-force: legacy AWX artifacts (mantenidos como referencia)
   ============================================================================ */

const Renderers = {

  _kpi(label, value) {
    return `<div class="ecp-kpi">
              <div class="ecp-kpi__value">${value ?? '—'}</div>
              <div class="ecp-kpi__label">${label}</div>
            </div>`;
  },

  _sevBadge(sev) {
    const map = {
      HEALTHY:  'severity-good',
      OK:       'severity-good',
      DEGRADED: 'severity-warn',
      WARNING:  'severity-warn',
      CRITICAL: 'severity-critical',
      UNKNOWN:  'severity-neutral',
    };
    const cls = map[(sev || '').toUpperCase()] || 'severity-neutral';
    return `<span class="severity-badge ${cls}">${sev || 'N/A'}</span>`;
  },

  _severityBadge(status, mapping) {
    const cls = mapping[(status || '').toUpperCase()] || 'severity-neutral';
    return `<span class="severity-badge ${cls}">${status || 'N/A'}</span>`;
  },

  _table(headers, rows, maxRows = 10) {
    if (!rows || rows.length === 0) {
      return '<p style="color:var(--text-muted);font-style:italic;">Sin datos.</p>';
    }
    const limited = rows.slice(0, maxRows);
    const head = headers.map(h => `<th>${h}</th>`).join('');
    const body = limited.map(r =>
      '<tr>' + r.map(c => `<td>${this._escapeHtml(String(c ?? ''))}</td>`).join('') + '</tr>'
    ).join('');
    return `<table class="ecp-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  },

  _escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  },

  _actions(awxUrl) {
    if (!awxUrl) return '';
    return `<div class="ecp-actions">
              <a href="${awxUrl}" target="_blank" class="ecp-btn">Ver job en AWX ↗</a>
              <button class="ecp-btn ecp-btn--secondary" onclick="window.scrollTo({top:0,behavior:'smooth'})">↑ Arriba</button>
            </div>`;
  },

  // ── health (System Health — lookup_infrastructure + lookup_sql) ─────────────
  health(a, awxUrl) {
    // El agente devuelve síntesis en texto; los artifacts pueden tener datos
    // parciales del ARM si el bridge expuso alguno. Este renderer muestra
    // una vista estructurada si los artifacts tienen el campo overall_severity,
    // sino cae a generic.
    const overall = a.overall_severity || a.severity;
    if (!overall) return this.generic(a, awxUrl);

    const label = a.env_label || (a.target_env === 'v1' ? 'TALENTO v1 legacy' : 'TALENTO v2 activo');

    const layerRows = [];
    if (a.aci)        layerRows.push(['Container (ACI)',  a.aci.state || '?', a.aci.severity || '?', `restarts: ${a.aci.restart_count ?? '?'}`]);
    if (a.appservice) layerRows.push(['App Service',      a.appservice.state || '?', a.appservice.severity || '?', a.appservice.availability_state || '?']);
    if (a.storage)    layerRows.push(['Storage Accounts', `${a.storage.total ?? '?'} cuentas`, a.storage.severity || '?', `no-HTTPS: ${a.storage.non_compliant_https ?? 0}`]);
    if (a.quotas)     layerRows.push(['Quotas vCPU',      a.quotas.quotas ? `${a.quotas.quotas[0]?.used ?? '?'}/${a.quotas.quotas[0]?.limit ?? '?'}` : '?', a.quotas.severity || '?', '']);

    return `
      <div style="margin-bottom:12px;">
        <h4 style="margin:0 0 4px;">🏥 System Health — ${this._escapeHtml(label)}</h4>
        <p style="margin:0;">Veredicto global: ${this._sevBadge(overall)}</p>
      </div>
      ${layerRows.length > 0 ? `
        <h5>Estado por capa</h5>
        ${this._table(['Capa', 'Estado', 'Severidad', 'Detalle'], layerRows)}
      ` : ''}
      ${this._actions(awxUrl)}
    `;
  },

  // ── errors (legacy AWX artifacts — mantenido) ────────────────────────────────
  errors(a, awxUrl) {
    // Si no hay artifacts de AWX, caer a generic
    if (!a || !a.severity_status) return this.generic(a, awxUrl);
    const sevMap = { CRITICAL: 'severity-critical', WARN: 'severity-warn', OK: 'severity-good' };
    return `
      <h4 style="margin-top:0;">🚨 Análisis de Errores</h4>
      <p>${this._severityBadge(a.severity_status, sevMap)}</p>
      <div class="ecp-kpi-grid">
        ${this._kpi('Errores', a.total_errors)}
        ${this._kpi('Warnings', a.total_warnings)}
        ${this._kpi('Containers', (a.affected_containers || []).length)}
        ${this._kpi('Rango (h)', a.time_range_hours)}
      </div>
      <h5>Top mensajes:</h5>
      ${this._table(['Mensaje', 'Conteo'], (a.top_messages || []).map(r => [r[0], r[1]]))}
      ${this._actions(awxUrl)}
    `;
  },

  // ── sox (legacy AWX artifacts) ───────────────────────────────────────────────
  sox(a, awxUrl) {
    if (!a || !a.audit_status) return this.generic(a, awxUrl);
    const sevMap = { SECURITY_INCIDENT: 'severity-critical', AUDIT_REVIEW: 'severity-warn', NORMAL: 'severity-good' };
    return `
      <h4 style="margin-top:0;">🔐 Auditoría SOX</h4>
      <p>${this._severityBadge(a.audit_status, sevMap)}</p>
      <div class="ecp-kpi-grid">
        ${this._kpi('Logins', a.total_login_events)}
        ${this._kpi('Usuarios únicos', a.unique_users)}
        ${this._kpi('Acciones priv.', a.total_privileged_actions)}
        ${this._kpi('Incidentes BD', a.total_security_incidents)}
      </div>
      <h5>Actividad por usuario:</h5>
      ${this._table(['Usuario', 'Tipo', 'Eventos'], a.login_breakdown || [])}
      ${this._actions(awxUrl)}
    `;
  },

  // ── brute-force (legacy AWX artifacts) ──────────────────────────────────────
  'brute-force'(a, awxUrl) {
    if (!a || !a.bruteforce_severity) return this.generic(a, awxUrl);
    const sevMap = { HIGH: 'severity-critical', MEDIUM: 'severity-warn', LOW: 'severity-good' };
    return `
      <h4 style="margin-top:0;">🛡️ Detección Brute Force</h4>
      <p>${this._severityBadge(a.bruteforce_severity || 'LOW', sevMap)}</p>
      <div class="ecp-kpi-grid">
        ${this._kpi('Sospechosos', a.suspicious_users_count ?? 0)}
        ${this._kpi('Failed logins', a.total_failed_logins ?? 0)}
        ${this._kpi('Umbral', a.failed_threshold)}
        ${this._kpi('Rango (h)', a.time_range_hours)}
      </div>
      <h5>Usuarios sobre umbral:</h5>
      ${this._table(['Usuario', 'Intentos'], a.suspicious_users || [])}
      ${this._actions(awxUrl)}
    `;
  },

  // ── snapshot (legacy AWX artifacts) ──────────────────────────────────────────
  snapshot(a, awxUrl) {
    if (!a || !a.n_tables_with_data) return this.generic(a, awxUrl);
    return `
      <h4 style="margin-top:0;">📊 Workspace Snapshot</h4>
      <div class="ecp-kpi-grid">
        ${this._kpi('Tablas con datos', a.n_tables_with_data)}
        ${this._kpi('Top tabla', this._escapeHtml(String(a.top_table_name || '—')))}
        ${this._kpi('Filas top tabla', a.top_table_rows)}
        ${this._kpi('Rango (h)', a.time_range_hours)}
      </div>
      ${this._table(['Tabla', 'Registros'], a.all_tables_summary || [])}
      ${this._actions(awxUrl)}
    `;
  },

  // ── generic (todos los escenarios v21 basados en síntesis del agente) ─────────
  generic(a, awxUrl) {
    // Sin artifacts AWX: el agente sintetiza en texto (renderResult agrega el bloque)
    if (!a || Object.keys(a).length === 0) {
      return `<p style="color:var(--text-muted);font-style:italic;">Sin artifacts estructurados — revisa el texto sintetizado por el agente.</p>`;
    }
    const rows = Object.entries(a).map(([k, v]) => [
      k,
      typeof v === 'object' ? JSON.stringify(v).slice(0, 200) : String(v).slice(0, 200),
    ]);
    return `<h4 style="margin-top:0;">🤖 Resultado</h4>${this._table(['Campo', 'Valor'], rows, 30)}${this._actions(awxUrl)}`;
  },
};
