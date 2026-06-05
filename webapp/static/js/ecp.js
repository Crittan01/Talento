/* ============================================================================
   ecp.js — Cliente del dashboard TALENTO Operations Console.
   Maneja: click en card → POST /api/run → abre SSE → renderiza eventos.
   ============================================================================ */

(function () {
  'use strict';

  const state = {
    activeRunId: null,
    activeEventSource: null,
    activeCard: null,
    activeRenderer: 'generic',
    awxUrl: null,
    artifacts: {},
    startTime: null,
    elapsedTimer: null,
    forceMockUrlParam: new URLSearchParams(window.location.search).get('mock') === '1',
    targetEnv: 'v2',      // instancia activa por default
    activeScope: 'completo', // scope del health check
  };

  const el = {
    cards: document.getElementById('sidebar'),  // v21: cards dentro de groups, no de cardsGrid
    sidebar: document.getElementById('sidebar'),
    welcome: document.getElementById('welcome'),
    runBanner: document.getElementById('runBanner'),
    runBannerTitle: document.getElementById('runBannerTitle'),
    runBannerIcon: document.getElementById('runBannerIcon'),
    panelElapsed: document.getElementById('panelElapsed'),
    panelClose: document.getElementById('panelClose'),
    filtersBadge: document.getElementById('filtersBadge'),
    timelineWrap: document.getElementById('timelineWrap'),
    timeline: document.getElementById('timeline'),
    resultWrap: document.getElementById('resultWrap'),
    result: document.getElementById('result'),
    modal: document.getElementById('freeTextModal'),
    modalInput: document.getElementById('freeTextInput'),
    modalRun: document.getElementById('freeTextRunBtn'),
    modalCancel: document.getElementById('freeTextCancelBtn'),
    modalCancelX: document.getElementById('freeTextCancel'),
    filterTimeRange: document.getElementById('filterTimeRange'),
    filterThreshold: document.getElementById('bruteThreshold'),   // embebido en card brute-force
    filterHint: document.getElementById('filterHint'),
    connStatus: document.getElementById('connStatus'),
    infoView: document.getElementById('infoView'),
    infoViewTitle: document.getElementById('infoViewTitle'),
    infoViewBody: document.getElementById('infoViewBody'),
    infoViewClose: document.getElementById('infoViewClose'),
    instanceToggle: document.getElementById('instanceToggle'),
    scopeGroup: document.getElementById('scopeGroup'),
    scopeButtons: document.getElementById('scopeButtons'),
    scopeRunBtn: document.getElementById('scopeRunBtn'),
    timeRangeGroup: document.getElementById('timeRangeGroup'),
    envBadge: document.getElementById('envBadge'),
    timelineEnvBadge: document.getElementById('timelineEnvBadge'),
    smartNav: document.getElementById('smartNav'),
    smartNavButtons: document.getElementById('smartNavButtons'),
    activeFiltersHint: document.getElementById('activeFiltersHint'),
    modalTitle: document.getElementById('modalTitle'),
    modalHint: document.getElementById('modalHint'),
  };

  // -------------------------------------------------------------------------
  // Filter bar — gestiona valores actuales y visibilidad del threshold
  // -------------------------------------------------------------------------
  function readFilters() {
    // bruteThreshold se lee dinámicamente porque el DOM podría no estar listo aún
    const bruteEl = document.getElementById('bruteThreshold');
    return {
      time_range_hours: el.filterTimeRange
        ? parseInt(el.filterTimeRange.value, 10) : 24,
      failed_threshold: bruteEl ? parseInt(bruteEl.value, 10) : 5,
      target_env: state.targetEnv,
      scope: state.activeScope,
    };
  }
  function updateFilterHint() {
    if (!el.filterHint) return;
    const f = readFilters();
    el.filterHint.textContent =
      `Instancia: ${f.target_env} · Últimas ${f.time_range_hours}h · Cambios aplican al próximo run.`;
  }
  [el.filterTimeRange].filter(Boolean).forEach(s => {
    s.addEventListener('change', () => { markCardsAsUsingFilters(); updateFilterHint(); });
  });

  function markCardsAsUsingFilters() {
    const f = readFilters();
    const isDefault = f.time_range_hours === 24;
    if (!el.cards) return;
    el.cards.querySelectorAll('.ecp-sidebar-card').forEach(c => {
      const accepts = (c.dataset.acceptsFilters || '').split(',').filter(Boolean);
      c.dataset.filterActive = (!isDefault && accepts.length > 0) ? 'true' : 'false';
    });
  }
  // Inicial
  updateFilterHint();
  markCardsAsUsingFilters();

  // -------------------------------------------------------------------------
  // Instance toggle (v1/v2)
  // -------------------------------------------------------------------------
  if (el.instanceToggle) {
    el.instanceToggle.addEventListener('click', (e) => {
      const btn = e.target.closest('.ecp-instance-btn');
      if (!btn) return;
      const env = btn.dataset.env;
      if (env === state.targetEnv) return;
      state.targetEnv = env;
      el.instanceToggle.querySelectorAll('.ecp-instance-btn').forEach(b =>
        b.classList.toggle('ecp-instance-btn--active', b.dataset.env === env));
      updateFilterHint();
    });
  }

  // -------------------------------------------------------------------------
  // Scope buttons (health check)
  // -------------------------------------------------------------------------
  if (el.scopeButtons) {
    el.scopeButtons.addEventListener('click', (e) => {
      const btn = e.target.closest('.ecp-scope-btn');
      if (!btn) return;
      const scope = btn.dataset.scope;
      state.activeScope = scope;
      el.scopeButtons.querySelectorAll('.ecp-scope-btn').forEach(b =>
        b.classList.toggle('ecp-scope-btn--active', b.dataset.scope === scope));
    });
  }

  // Mostrar scope selector solo para el escenario infra-health-check
  function updateScopeVisibility(scenarioId) {
    if (!el.scopeGroup) return;
    el.scopeGroup.style.display = scenarioId === 'infra-health-check' ? 'flex' : 'none';
  }

  // Actualizar visibilidad y hints según los filtros que acepta el escenario
  const HINT_BY_SCENARIO = {
    'sox-audit':          '⏱ Sin efecto — audita las últimas ~3h del sistema (tiempo real)',
    'brute-force':        '⏱ Sin efecto — analiza las últimas ~3h del sistema (tiempo real)',
    'infra-health-check': '⏱ Sin efecto — consulta el estado actual de Azure ARM (instantáneo)',
    'auto-remediate-restart': '⏱ Sin efecto — acción sobre estado actual',
    'free-text':          'Instancia activa: v' + (state.targetEnv || '2') + ' · El agente decide la ventana',
  };

  function updateFilterVisibility(scenarioId, acceptsFilters) {
    const hasTime = (acceptsFilters || []).includes('time_range_hours');

    // Dimear / activar el grupo de tiempo
    if (el.timeRangeGroup) {
      el.timeRangeGroup.classList.toggle('ecp-filterbar__group--inactive', !hasTime);
      if (!hasTime) {
        el.timeRangeGroup.setAttribute('title',
          'Este escenario no usa ventana de tiempo — los datos provienen de otra fuente');
      } else {
        el.timeRangeGroup.removeAttribute('title');
      }
    }

    // Hint contextual
    if (el.filterHint) {
      if (hasTime) {
        const hrs = el.filterTimeRange ? el.filterTimeRange.value : 24;
        el.filterHint.innerHTML =
          `⏱ Ventana <strong>${hrs}h</strong> aplica · Instancia: <strong>${state.targetEnv}</strong>`;
      } else {
        el.filterHint.textContent =
          HINT_BY_SCENARIO[scenarioId] ||
          `Instancia: ${state.targetEnv} · El filtro de tiempo no aplica a este escenario`;
      }
    }
  }

  // Reset: vuelve al estado neutral (sin escenario seleccionado)
  function resetFilterVisibility() {
    if (el.timeRangeGroup) {
      el.timeRangeGroup.classList.remove('ecp-filterbar__group--inactive');
      el.timeRangeGroup.removeAttribute('title');
    }
    updateFilterHint();
  }

  // -------------------------------------------------------------------------
  // Connection status — poll /healthz cada 15s
  // -------------------------------------------------------------------------
  function setConnPill(svc, state) {
    const pill = el.connStatus.querySelector(`[data-svc="${svc}"]`);
    if (pill) pill.setAttribute('data-state', state);
  }
  function initConnStatus() {
    ['foundry', 'awx', 'teams'].forEach(s => setConnPill(s, 'unknown'));
  }
  async function pollHealth() {
    try {
      const r = await fetch('/healthz');
      if (r.ok) {
        // El dashboard sirviendo /healthz no garantiza que Foundry/AWX/Teams estén
        // OK — pero al menos confirma que el bridge respira. Marcamos como ok
        // optimisticamente; en errores de run los pills se ponen warn/error.
        setConnPill('foundry', 'ok');
        setConnPill('awx', 'ok');
        setConnPill('teams', 'ok');
      } else {
        setConnPill('foundry', 'error');
      }
    } catch {
      setConnPill('foundry', 'error');
      setConnPill('awx', 'error');
    }
  }
  initConnStatus();
  pollHealth();
  setInterval(pollHealth, 15000);

  // -------------------------------------------------------------------------
  // Card click handler
  // -------------------------------------------------------------------------
  // data-stop-click="true" ya se chequea dentro del handler principal (line ~236).
  // No se necesitan listeners en capture mode — causarían interferencia.

  el.cards.addEventListener('click', (e) => {
    const card = e.target.closest('.ecp-sidebar-card');
    if (!card) return;
    if (card.classList.contains('is-running')) return; // ya activa
    // Evitar trigger si el click fue dentro del filtro inline
    if (e.target.closest('[data-stop-click="true"]')) return;

    // Cards de info NO disparan run (las maneja sidebar.addEventListener via data-info-view)
    if (card.dataset.infoView) return;

    // Roadmap (en habilitacion): render explicativo en el panel principal, sin alert nativo.
    if (card.dataset.tier === 'pending') {
      const reason = card.dataset.pendingReason || card.title || 'En habilitacion';
      const title = card.querySelector('.ecp-sidebar-card__title')?.textContent || 'Escenario pendiente';
      if (el && el.timeline) {
        el.timeline.innerHTML = `
          <div class="info-finding info-finding--pending" style="margin:12px;padding:16px;border-left:4px solid #f0ad4e;background:#fff8e1;border-radius:4px;">
            <h3 style="margin-top:0;color:#8a6d3b;">⏳ ${title} — capacidad en habilitacion</h3>
            <p style="line-height:1.5;color:#5c4b1f;">${reason}</p>
            <p style="font-size:12px;color:#8a6d3b;margin-bottom:0;">
              Cuando el equipo de plataforma habilite la capacidad faltante, este escenario se reactiva automaticamente sin cambios en el codigo.
              Ver <b>Estado del ambiente</b> en el panel lateral para el detalle tecnico.
            </p>
          </div>`;
        if (el.resultWrap) el.resultWrap.style.display = 'none';
        if (el.infoView) el.infoView.style.display = 'none';
      }
      return;
    }

    const sid = card.dataset.scenarioId;
    const renderer = card.dataset.renderer;
    const freeText = card.dataset.freeText === 'true';
    const freeTextLabel = card.dataset.freeTextLabel || 'Pregunta libre al agente';
    const freeTextPlaceholder = card.dataset.freeTextPlaceholder || 'Escribe tu pregunta...';
    const acceptsFilters = (card.dataset.acceptsFilters || '').split(',').filter(Boolean);
    updateScopeVisibility(sid);
    updateFilterVisibility(sid, acceptsFilters);

    // Determinar qué filtros aplican a esta card
    const allFilters = readFilters();
    const filters = {};
    acceptsFilters.forEach(f => {
      if (allFilters[f] != null) filters[f] = allFilters[f];
    });
    // target_env siempre se incluye
    filters.target_env = allFilters.target_env;

    // infra-health-check: mostrar scope y esperar confirmación antes de correr
    if (sid === 'infra-health-check') {
      state._pendingHealthCard = card;
      state._pendingHealthRenderer = renderer;
      state._pendingHealthFilters = filters;
      if (el.scopeRunBtn) el.scopeRunBtn.style.display = 'inline-block';
      document.querySelectorAll('.ecp-sidebar-card.is-scope-pending')
        .forEach(c => c.classList.remove('is-scope-pending'));
      card.classList.add('is-scope-pending');
      return;
    }

    if (freeText) {
      openFreeTextModal(card, sid, renderer, filters, freeTextLabel, freeTextPlaceholder);
    } else {
      runScenario(card, sid, renderer, null, filters);
    }
  });

  el.panelClose.addEventListener('click', closePanel);

  // Hover preview eliminado — la visibilidad de filtros se actualiza en click.

  // scopeRunBtn — ejecuta infra-health-check con el scope y env seleccionados
  if (el.scopeRunBtn) {
    el.scopeRunBtn.addEventListener('click', () => {
      if (!state._pendingHealthCard) return;
      const card = state._pendingHealthCard;
      const renderer = state._pendingHealthRenderer || 'health';
      const filters = Object.assign({}, state._pendingHealthFilters || {}, {
        scope: state.activeScope,
        target_env: state.targetEnv,
      });
      card.classList.remove('is-scope-pending');
      el.scopeRunBtn.style.display = 'none';
      state._pendingHealthCard = null;
      state._pendingHealthRenderer = null;
      state._pendingHealthFilters = null;
      runScenario(card, 'infra-health-check', renderer, null, filters);
    });
  }

  // -------------------------------------------------------------------------
  // Free-text modal
  // -------------------------------------------------------------------------
  function openFreeTextModal(card, sid, renderer, filters, label, placeholder) {
    el.modalInput.value = '';
    el.modalInput.placeholder = placeholder || 'Escribe aqui...';
    if (el.modalTitle && label) el.modalTitle.textContent = label;
    if (el.modalHint) el.modalHint.textContent = placeholder || 'Escribe una pregunta operativa.';
    el.modal.classList.add('is-open');
    el.modalInput.focus();
    state._pendingCard = card;
    state._pendingSid = sid;
    state._pendingRenderer = renderer;
    state._pendingFilters = filters || {};
  }
  function closeFreeTextModal() {
    el.modal.classList.remove('is-open');
    state._pendingCard = null;
    state._pendingFilters = null;
  }
  el.modalCancel.addEventListener('click', closeFreeTextModal);
  el.modalCancelX.addEventListener('click', closeFreeTextModal);
  el.modalRun.addEventListener('click', () => {
    const txt = el.modalInput.value.trim();
    if (!txt) {
      alert('Escribe algo primero.');
      el.modalInput.focus();
      return;
    }
    // Guards defensivos — si por alguna razon el state no se seteo correctamente
    // al abrir el modal, mostrar un mensaje visible en lugar de TypeError silenciosa
    if (!state._pendingCard || !state._pendingSid) {
      alert('Estado interno inconsistente: no se identifico el escenario al abrir el modal. '
            + 'Cierra el modal con la X y vuelve a clickear la card del escenario.');
      console.error('Modal Run sin _pendingCard/_pendingSid', {
        card: state._pendingCard,
        sid: state._pendingSid,
        renderer: state._pendingRenderer,
      });
      return;
    }
    const filters = state._pendingFilters || {};
    const card = state._pendingCard;
    const sid = state._pendingSid;
    const renderer = state._pendingRenderer;
    closeFreeTextModal();
    runScenario(card, sid, renderer, txt, filters).catch(err => {
      console.error('runScenario crashed:', err);
      alert('Error al ejecutar: ' + (err && err.message ? err.message : err));
    });
  });

  // -------------------------------------------------------------------------
  // Run scenario
  // -------------------------------------------------------------------------
  async function runScenario(card, scenarioId, renderer, freeText, filters) {
    if (state.activeRunId) {
      alert('Hay un escenario en ejecución. Espera a que termine o ciérralo.');
      return;
    }

    card.classList.add('is-running');
    state.activeCard = card;
    state.activeRenderer = renderer;
    state.activeFilters = filters || {};
    state.awxUrl = null;
    state.artifacts = {};

    // Cambiar layout: ocultar welcome y CUALQUIER info view abierta previa,
    // mostrar run banner + timeline. (Sin esto, si el usuario vio antes una
    // vista de Informacion del Sistema, esa view cubre el run en marcha.)
    el.welcome.style.display = 'none';
    if (el.infoView) {
      el.infoView.style.display = 'none';
      document.querySelectorAll('.ecp-sidebar-card--info').forEach(c =>
        c.classList.remove('is-active'));
    }
    el.runBanner.style.display = 'flex';
    el.timelineWrap.style.display = 'block';
    el.resultWrap.style.display = 'none'; // se muestra cuando llega agent.final

    // Poblar banner
    const cardIcon = card.querySelector('.ecp-sidebar-card__icon').textContent;
    const cardTitle = card.querySelector('.ecp-sidebar-card__title').textContent;
    el.runBannerIcon.textContent = cardIcon;
    el.runBannerTitle.textContent = cardTitle;

    // Badge de instancia activa
    if (el.envBadge) {
      el.envBadge.textContent = filters.target_env === 'v1' ? '🏛️ v1 legacy' : '⭐ v2 activo';
      el.envBadge.className = `ecp-env-badge ecp-env-badge--${filters.target_env}`;
      el.envBadge.style.display = 'inline-block';
    }
    if (el.timelineEnvBadge) {
      el.timelineEnvBadge.textContent = filters.target_env === 'v1' ? 'v1' : 'v2';
      el.timelineEnvBadge.className = `ecp-section-env ecp-section-env--${filters.target_env}`;
    }

    // Badge de filtros aplicados
    const filterStr = formatFiltersBadge(filters);
    if (filterStr) {
      el.filtersBadge.textContent = filterStr;
      el.filtersBadge.style.display = 'inline-block';
    } else {
      el.filtersBadge.style.display = 'none';
    }

    // Hint de filtros activos en el timeline
    if (el.activeFiltersHint) {
      const parts = [`Instancia: ${filters.target_env}`];
      if (filters.scope && filters.scope !== 'completo') parts.push(`Alcance: ${filters.scope}`);
      if (filters.time_range_hours && filters.time_range_hours !== 24) parts.push(`${filters.time_range_hours}h`);
      el.activeFiltersHint.innerHTML = '⚙️ ' + parts.join(' · ');
      el.activeFiltersHint.style.display = 'block';
    }

    el.timeline.innerHTML = '';
    el.result.innerHTML = '';

    state.startTime = Date.now();
    startElapsedTimer();

    // Evento sintético: anunciar filtros aplicados en el timeline
    const filterMsg = Object.keys(filters || {}).length > 0
      ? Object.entries(filters).map(([k, v]) => `${k}=<strong>${v}</strong>`).join(', ')
      : '<em>defaults</em>';
    appendTimeline('info', '⚙️', `Filtros aplicados: ${filterMsg}`);

    let resp;
    try {
      resp = await fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario_id: scenarioId,
          free_text: freeText,
          mock: state.forceMockUrlParam,
          filters: filters || {},
        }),
      });
    } catch (err) {
      appendTimeline('error', '⚠️', 'No se pudo conectar al servidor: ' + err.message);
      finishRun();
      return;
    }

    if (!resp.ok) {
      const errBody = await resp.text();
      appendTimeline('error', '⚠️', `Error HTTP ${resp.status}: ${errBody}`);
      finishRun();
      return;
    }

    const data = await resp.json();
    state.activeRunId = data.run_id;
    appendTimeline('info', '🟢', `Run iniciado <code>${data.run_id.slice(0, 8)}…</code> (modo: ${data.mode})`);

    // Conectar SSE
    state.activeEventSource = new EventSource(`/api/run/${data.run_id}/stream`);
    state.activeEventSource.onmessage = (e) => {
      let event;
      try { event = JSON.parse(e.data); } catch { return; }
      handleEvent(event);
    };
    state.activeEventSource.onerror = () => {
      appendTimeline('error', '⚠️', 'Conexión SSE perdida.');
      finishRun();
    };
  }

  // -------------------------------------------------------------------------
  // SSE event handler
  // -------------------------------------------------------------------------
  function handleEvent(evt) {
    const t = evt.type;

    if (t === 'agent.received') {
      appendTimeline('info', '👤', `Pregunta recibida — agente <code>${evt.agent}</code> (max_hops=${evt.max_hops}).`);
    }
    else if (t === 'agent.connecting') {
      appendTimeline('info', '🔌', 'Conectando a Foundry…');
    }
    else if (t === 'agent.setup_version') {
      appendTimeline('info', '⚙️', 'Registrando nueva versión del agente…');
    }
    else if (t === 'agent.version_ready') {
      appendTimeline('info', '✓', `Agente versión <code>${evt.name}:${evt.version}</code> activo.`);
    }
    else if (t === 'agent.hop') {
      appendTimeline('info', '🔄', `Hop ${evt.hop} — el agente está razonando…`);
    }
    else if (t === 'tool.call') {
      const a = evt.args || {};
      let niceArgs;
      if (evt.tool === 'query_log_analytics') {
        niceArgs = `<code>${escapeHtml(String(a.query || '').slice(0, 200))}</code>`;
      } else if (evt.tool === 'run_awx_job_template') {
        niceArgs = `template_id=<code>${escapeHtml(String(a.template_id ?? ''))}</code>`;
      } else if (evt.tool === 'lookup_runtime_logs') {
        const parts = [];
        if (a.modo) parts.push(`modo=<code>${escapeHtml(String(a.modo))}</code>`);
        if (a.usuario) parts.push(`usuario=<code>${escapeHtml(String(a.usuario))}</code>`);
        if (a.minutos) parts.push(`minutos=<code>${a.minutos}</code>`);
        niceArgs = parts.join(' ') || '<em>(sin args)</em>';
      } else if (evt.tool === 'lookup_correlation_id') {
        niceArgs = `correlation_id=<code>${escapeHtml(String(a.correlation_id || ''))}</code> ventana=<code>${a.time_range_hours || '?'}h</code>`;
      } else if (evt.tool === 'tlnt_explorer') {
        const c = a.codigo ? `codigo=<code>${escapeHtml(String(a.codigo))}</code>` : '<em>(ranking)</em>';
        niceArgs = `${c} ventana=<code>${a.time_range_hours || '?'}h</code>`;
      } else if (evt.tool === 'user_activity') {
        niceArgs = `usuario=<code>${escapeHtml(String(a.usuario || ''))}</code> ventana=<code>${a.time_range_hours || '?'}h</code>`;
      } else {
        niceArgs = `<code>${escapeHtml(JSON.stringify(a).slice(0, 200))}</code>`;
      }
      appendTimeline('kql', '🛠️', `Tool <strong>${escapeHtml(evt.tool)}</strong> → ${niceArgs}`);
    }
    else if (t === 'tool.kql.done') {
      appendTimeline('kql', '✓', `KQL OK (${evt.elapsed_seconds}s) — ${evt.rows} filas`);
    }
    else if (t === 'tool.kql.error') {
      appendTimeline('error', '⚠️', `KQL ERROR (${evt.elapsed_seconds}s) — ${escapeHtml(evt.error || '')}`);
    }
    // --- ARM tools (lookup_infrastructure, lookup_sql) ---
    else if (t === 'tool.arm.fetch') {
      appendTimeline('kql', '🔌', `Consultando Azure ARM: ${escapeHtml(evt.source || 'infraestructura')}`);
    }
    else if (t === 'tool.arm.done') {
      const sevBadge = evt.severity
        ? `&nbsp;<strong class="sev-${(evt.severity || '').toLowerCase()}">${escapeHtml(evt.severity)}</strong>` : '';
      appendTimeline('kql', '✓', `ARM OK (${evt.elapsed_seconds}s) — mode=${escapeHtml(evt.mode || evt.tool || '')}${sevBadge}`);
    }
    else if (t === 'tool.arm.error') {
      appendTimeline('error', '⚠️', `ARM ERROR (${evt.elapsed_seconds}s) — ${escapeHtml(evt.error || '')}`);
    }
    // --- App Insights ---
    else if (t === 'tool.ai.fetch') {
      appendTimeline('kql', '📊', `App Insights: ${escapeHtml(evt.source || '')}`);
    }
    else if (t === 'tool.ai.done') {
      appendTimeline('kql', '✓', `App Insights OK (${evt.elapsed_seconds}s) — ${evt.rows} filas`);
    }
    else if (t === 'tool.ai.error') {
      appendTimeline('error', '⚠️', `App Insights ERROR (${evt.elapsed_seconds}s) — ${escapeHtml(evt.error || '')}`);
    }
    else if (t === 'tool.runtime.fetch') {
      appendTimeline('kql', '📡', `Leyendo runtime: ${escapeHtml(evt.source || 'actividad reciente del sistema')}`);
    }
    else if (t === 'tool.runtime.done') {
      appendTimeline('kql', '✓', `Runtime OK (${evt.elapsed_seconds}s) — ${evt.rows} filas / ${evt.buffer_lineas} eventos en buffer`);
    }
    else if (t === 'tool.runtime.error') {
      appendTimeline('error', '⚠️', `Runtime ERROR (${evt.elapsed_seconds}s) — ${escapeHtml(evt.error || '')}`);
    }
    else if (t === 'tool.awx.launched') {
      state.awxUrl = evt.awx_url;
      appendTimeline('awx', '🚀', `AWX job <code>${evt.job_id}</code> lanzado (template ${evt.template_id}).`);
    }
    else if (t === 'tool.awx.polling') {
      // Actualiza el último item de polling en lugar de crear nuevo (menos spam)
      updateOrAppendPolling(evt);
    }
    else if (t === 'tool.awx.done') {
      Object.assign(state.artifacts, evt.artifacts || {});
      const statusBadge = evt.status === 'successful' ? '✅' : '❌';
      appendTimeline('awx', statusBadge,
        `AWX job <code>${evt.job_id}</code>: <strong>${evt.status}</strong> (${evt.elapsed_seconds}s) — adaptive card a Teams enviada.`);
    }
    else if (t === 'tool.awx.error') {
      appendTimeline('error', '⚠️', `AWX ERROR (${evt.elapsed_seconds}s) — ${escapeHtml(evt.error || '')}`);
    }
    else if (t === 'tool.awx.timeout') {
      appendTimeline('error', '⏱', `AWX timeout — job ${evt.job_id} no completó en 120s.`);
    }
    else if (t === 'agent.hop_limit') {
      appendTimeline('error', '⚠️', `Límite de ${evt.max_hops} hops alcanzado.`);
    }
    else if (t === 'agent.final') {
      appendTimeline('final', '🦎', `Síntesis final lista (${evt.elapsed_seconds}s total).`);
      renderResult(evt.text);
    }
    else if (t === 'agent.error') {
      appendTimeline('error', '💥', `Error del agente: ${escapeHtml(evt.error || 'desconocido')}`);
    }
    else if (t === 'done') {
      finishRun();
    }
    else {
      // Evento no reconocido — log sutil
      appendTimeline('info', '·', `<em>${t}</em>`);
    }
  }

  function updateOrAppendPolling(evt) {
    let pollNode = el.timeline.querySelector(`.poll-${evt.job_id}`);
    // Estimacion visual: la mayoria de jobs duran 10-15s
    const expected = 15;
    const pct = Math.min(95, (evt.elapsed_seconds / expected) * 100);
    const isRunning = evt.status === 'running' || evt.status === 'pending' || evt.status === 'waiting';
    const barClass = isRunning ? 'ecp-awx-progress__bar--animated' : '';
    const text = `
      AWX polling — job <code>${evt.job_id}</code> · estado <strong>${evt.status}</strong> (${evt.elapsed_seconds}s)
      <div class="ecp-awx-progress">
        <div class="ecp-awx-progress__bar ${barClass}" style="width: ${pct}%;"></div>
      </div>`;
    if (pollNode) {
      pollNode.querySelector('.ecp-timeline__text').innerHTML = text;
    } else {
      const node = renderTimelineItem('awx', '⏳', text);
      node.classList.add(`poll-${evt.job_id}`);
      el.timeline.appendChild(node);
      autoscrollTimeline();
    }
  }

  // (helpers de formato ahora en formatFiltersBadge, ver más arriba)

  // -------------------------------------------------------------------------
  // Result render — usa el renderer del scenario
  // -------------------------------------------------------------------------
  function renderResult(finalText) {
    const renderer = Renderers[state.activeRenderer] || Renderers.generic;
    let resultHtml;
    try {
      resultHtml = renderer.call(Renderers, state.artifacts, state.awxUrl);
    } catch (err) {
      console.error('Renderer error:', err);
      resultHtml = `<p style="color: var(--critical);">Error renderizando: ${escapeHtml(err.message)}</p>`;
    }
    // Render del texto del agente como markdown si marked.js cargó, fallback a escape
    let agentHtml;
    if (window.marked) {
      try {
        agentHtml = marked.parse(finalText || '');
      } catch (err) {
        console.warn('marked.parse error:', err);
        agentHtml = escapeHtml(finalText);
      }
    } else {
      agentHtml = escapeHtml(finalText);
    }
    el.result.innerHTML = resultHtml + `
      <div class="ecp-agent-reply">
        <div class="ecp-agent-reply__header">
          <img src="/static/img/iguana.svg" alt="Iguana" class="ecp-iguana ecp-iguana--sm">
          RESPUESTA DEL AGENTE
        </div>
        ${agentHtml}
      </div>
    `;
    el.resultWrap.style.display = 'block';

    // Smart navigation: extrae entidades del texto y genera botones de acción
    buildSmartNav(finalText || '');
  }

  // -------------------------------------------------------------------------
  // Smart navigation — extrae entidades del texto del agente y genera botones
  // -------------------------------------------------------------------------
  const UUID_RE = /\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b/gi;
  const TLNT_RE = /\b(TLNT-\d{3})\b/g;
  const USER_RE = /\b(nvivas|cmedina|jtorres|jparra|nadie-\d+)\b/gi;
  const HIGH_RE = /\b(HIGH|CRITICAL|DEGRADED)\b/;

  function buildSmartNav(text) {
    if (!el.smartNav || !el.smartNavButtons) return;
    const buttons = [];
    const addedUUIDs = new Set();
    const addedTLNTs = new Set();
    const addedUsers = new Set();

    // Correlation IDs
    let m;
    UUID_RE.lastIndex = 0;
    while ((m = UUID_RE.exec(text)) !== null && addedUUIDs.size < 3) {
      const id = m[1];
      if (addedUUIDs.has(id)) continue;
      addedUUIDs.add(id);
      const short = id.slice(0, 8) + '…';
      buttons.push({ label: `🔍 Trazar ${short}`, action: 'correlation-trace', value: id });
    }

    // TLNT codes
    TLNT_RE.lastIndex = 0;
    while ((m = TLNT_RE.exec(text)) !== null && addedTLNTs.size < 3) {
      const code = m[1];
      if (addedTLNTs.has(code)) continue;
      addedTLNTs.add(code);
      buttons.push({ label: `📚 Explorar ${code}`, action: 'tlnt-explorer', value: code });
    }

    // Usuarios conocidos
    USER_RE.lastIndex = 0;
    while ((m = USER_RE.exec(text)) !== null && addedUsers.size < 2) {
      const user = m[1].toLowerCase();
      if (addedUsers.has(user) || user.startsWith('nadie-')) continue;
      addedUsers.add(user);
      buttons.push({ label: `👤 Auditar ${user}`, action: 'sox-audit', value: user });
      buttons.push({ label: `📊 Actividad ${user}`, action: 'user-activity', value: user });
    }

    // Severidad alta → brute force
    if (HIGH_RE.test(text) && !addedUsers.size) {
      buttons.push({ label: `🛡️ Verificar brute force`, action: 'brute-force', value: '' });
    }

    if (buttons.length === 0) {
      el.smartNav.style.display = 'none';
      return;
    }

    el.smartNavButtons.innerHTML = buttons.map(b =>
      `<button class="ecp-smart-btn" data-action="${escapeHtml(b.action)}" data-value="${escapeHtml(b.value)}">${escapeHtml(b.label)}</button>`
    ).join('');
    el.smartNav.style.display = 'flex';

    // Click handler — lanza el escenario relacionado con el valor pre-relleno
    el.smartNavButtons.querySelectorAll('.ecp-smart-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const action = btn.dataset.action;
        const value = btn.dataset.value;
        const card = document.querySelector(`[data-scenario-id="${action}"]`);
        if (!card) return;
        const renderer = card.dataset.renderer || 'generic';
        const filters = readFilters();
        // Si el escenario acepta free_text, lanzarlo directamente con el valor
        if (card.dataset.freeText === 'true' && value) {
          runScenario(card, action, renderer, value, filters);
        } else {
          runScenario(card, action, renderer, null, filters);
        }
      });
    });
  }

  function formatFiltersBadge(filters) {
    // Devuelve string del badge si los filtros difieren de defaults, o "" si no
    if (!filters || Object.keys(filters).length === 0) return '';
    const parts = [];
    if (filters.time_range_hours != null && filters.time_range_hours !== 24) {
      parts.push(`${filters.time_range_hours}h`);
    }
    if (filters.failed_threshold != null && filters.failed_threshold !== 5) {
      parts.push(`umbral ${filters.failed_threshold}`);
    }
    if (parts.length === 0) return ''; // todos en defaults, no mostrar badge
    return `Filtros: ${parts.join(' · ')}`;
  }

  // -------------------------------------------------------------------------
  // Timeline helpers
  // -------------------------------------------------------------------------
  function appendTimeline(cls, icon, text) {
    const node = renderTimelineItem(cls, icon, text);
    el.timeline.appendChild(node);
    autoscrollTimeline();
  }

  function renderTimelineItem(cls, icon, text) {
    const div = document.createElement('div');
    div.className = `ecp-timeline__item ecp-timeline__item--${cls}`;
    const ts = ((Date.now() - state.startTime) / 1000).toFixed(1) + 's';
    div.innerHTML = `
      <span class="ecp-timeline__icon">${icon}</span>
      <span class="ecp-timeline__text">${text}</span>
      <span class="ecp-timeline__time">${ts}</span>
    `;
    return div;
  }

  function autoscrollTimeline() {
    el.timeline.scrollTop = el.timeline.scrollHeight;
  }

  // -------------------------------------------------------------------------
  // Lifecycle
  // -------------------------------------------------------------------------
  function startElapsedTimer() {
    el.panelElapsed.textContent = '0.0s';
    state.elapsedTimer = setInterval(() => {
      const s = ((Date.now() - state.startTime) / 1000).toFixed(1);
      el.panelElapsed.textContent = `${s}s`;
    }, 100);
  }

  function stopElapsedTimer() {
    if (state.elapsedTimer) {
      clearInterval(state.elapsedTimer);
      state.elapsedTimer = null;
    }
  }

  function finishRun() {
    if (state.activeEventSource) {
      state.activeEventSource.close();
      state.activeEventSource = null;
    }
    if (state.activeCard) {
      state.activeCard.classList.remove('is-running');
    }
    stopElapsedTimer();
    state.activeRunId = null;
  }

  function closePanel() {
    finishRun();
    el.runBanner.style.display = 'none';
    el.timelineWrap.style.display = 'none';
    el.resultWrap.style.display = 'none';
    el.welcome.style.display = 'block';
    el.timeline.innerHTML = '';
    el.result.innerHTML = '';
    el.filtersBadge.style.display = 'none';
    if (el.envBadge) el.envBadge.style.display = 'none';
    if (el.smartNav) el.smartNav.style.display = 'none';
    if (el.activeFiltersHint) el.activeFiltersHint.style.display = 'none';
    if (el.scopeRunBtn) el.scopeRunBtn.style.display = 'none';
    document.querySelectorAll('.ecp-sidebar-card.is-scope-pending')
      .forEach(c => c.classList.remove('is-scope-pending'));
    state._pendingHealthCard = null;
    state.activeCard = null;
    resetFilterVisibility();
  }

  function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // ===========================================================================
  // Info views — 5 paneles informativos (no son runs del agente)
  // ===========================================================================
  const INFO_VIEW_META = {
    cert:      { title: '🔒 Certificación SOX',     endpoint: '/api/info/cert',      renderer: 'renderCert' },
    agent:     { title: '🤖 Agente IA',              endpoint: '/api/info/agent',     renderer: 'renderAgent' },
    knowledge: { title: '📚 Knowledge Base',         endpoint: '/api/info/knowledge', renderer: 'renderKnowledge' },
    findings:  { title: '⚠️ Estado del ambiente',        endpoint: '/api/info/findings',  renderer: 'renderFindings' },
    runs:      { title: '📈 Historial de Runs',      endpoint: '/api/info/runs',      renderer: 'renderRuns' },
  };

  // Delegacion de click sobre cards de informacion (en sidebar pero fuera de cardsGrid)
  if (el.sidebar) {
    el.sidebar.addEventListener('click', (e) => {
      const card = e.target.closest('[data-info-view]');
      if (!card) return;
      const viewKey = card.dataset.infoView;
      openInfoView(viewKey);
    });
  }

  if (el.infoViewClose) {
    el.infoViewClose.addEventListener('click', closeInfoView);
  }

  async function openInfoView(viewKey) {
    const meta = INFO_VIEW_META[viewKey];
    if (!meta) return;

    // Cerrar run activo si lo hay y limpiar UI de welcome/result
    if (state.activeRunId) closePanel();
    el.welcome.style.display = 'none';
    el.runBanner.style.display = 'none';
    el.timelineWrap.style.display = 'none';
    el.resultWrap.style.display = 'none';

    // Marcar card activa
    document.querySelectorAll('.ecp-sidebar-card--info').forEach(c => c.classList.remove('is-active'));
    const card = document.querySelector(`[data-info-view="${viewKey}"]`);
    if (card) card.classList.add('is-active');

    el.infoView.style.display = 'block';
    el.infoViewTitle.textContent = meta.title;
    el.infoViewBody.innerHTML = '<div class="ecp-infoview__loading">Cargando…</div>';

    try {
      const resp = await fetch(meta.endpoint);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      const renderFn = INFO_RENDERERS[meta.renderer];
      el.infoViewBody.innerHTML = renderFn ? renderFn(data) : `<pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
    } catch (err) {
      el.infoViewBody.innerHTML = `<div class="ecp-infoview__error">Error: ${escapeHtml(err.message)}</div>`;
    }
  }

  function closeInfoView() {
    el.infoView.style.display = 'none';
    el.infoViewBody.innerHTML = '';
    el.welcome.style.display = 'block';
    document.querySelectorAll('.ecp-sidebar-card--info').forEach(c => c.classList.remove('is-active'));
  }

  // ---------- Renderers de cada vista ----------------------------------------
  const INFO_RENDERERS = {
    renderCert(d) {
      const catRows = d.categories.map(c => `
        <tr>
          <td><code>${escapeHtml(c.name)}</code></td>
          <td>${c.n}</td>
          <td>${c.safety_pass}/${c.n}</td>
          <td>${c.functional_pass}/${c.n}</td>
          <td>${c.verdict_pass}/${c.n}</td>
          <td>${escapeHtml(c.threshold)}</td>
          <td>${c.ok ? '<span class="badge badge--pass">✓ OK</span>' : '<span class="badge badge--fail">✗ FAIL</span>'}</td>
        </tr>
      `).join('');

      const layers = d.defense_in_depth.map(l => `
        <li><strong>Capa ${l.layer}</strong> — ${escapeHtml(l.name)} (${escapeHtml(l.engine)}): ${escapeHtml(l.coverage)}</li>
      `).join('');

      const traj = d.trajectory.map(t => `
        <tr>
          <td><code>${escapeHtml(t.version)}</code></td>
          <td>${escapeHtml(t.model)}</td>
          <td>${t.guard ? '✓' : '—'}</td>
          <td>${escapeHtml(t.result)}</td>
        </tr>
      `).join('');

      const sox = d.sox_guarantees.map(g => `<li>${escapeHtml(g)}</li>`).join('');

      return `
        <div class="info-block">
          <div class="info-summary">
            <div class="info-summary__metric">
              <span class="info-summary__label">Versión agente</span>
              <span class="info-summary__value">${escapeHtml(d.agent_version)}</span>
            </div>
            <div class="info-summary__metric">
              <span class="info-summary__label">Modelo</span>
              <span class="info-summary__value">${escapeHtml(d.model)}</span>
            </div>
            <div class="info-summary__metric">
              <span class="info-summary__label">Safety</span>
              <span class="info-summary__value info-summary__value--pass">${escapeHtml(d.totals.safety)}</span>
            </div>
            <div class="info-summary__metric">
              <span class="info-summary__label">Functional</span>
              <span class="info-summary__value info-summary__value--pass">${escapeHtml(d.totals.functional)}</span>
            </div>
            <div class="info-summary__metric">
              <span class="info-summary__label">Verdict global</span>
              <span class="info-summary__value info-summary__value--pass">${escapeHtml(d.totals.verdict)}</span>
            </div>
          </div>

          <p><a class="info-cta" href="${escapeHtml(d.portal_foundry_url)}" target="_blank" rel="noopener">
            📊 Ver dashboard nativo en Portal Foundry →
          </a></p>

          <h4>Resultado por categoría</h4>
          <table class="info-table">
            <thead><tr><th>Categoría</th><th>N</th><th>Safety</th><th>Functional</th><th>Verdict</th><th>Threshold</th><th>Status</th></tr></thead>
            <tbody>${catRows}</tbody>
          </table>

          <h4>Defensa en profundidad</h4>
          <ul class="info-list">${layers}</ul>

          <h4>Trayectoria de versiones</h4>
          <table class="info-table">
            <thead><tr><th>Versión</th><th>Modelo</th><th>Guard</th><th>Resultado</th></tr></thead>
            <tbody>${traj}</tbody>
          </table>

          <h4>Garantías SOX cumplidas</h4>
          <ul class="info-list">${sox}</ul>
        </div>
      `;
    },

    renderAgent(d) {
      const tools = d.tools.map(t => `
        <tr>
          <td><code>${escapeHtml(t.name)}</code></td>
          <td>${escapeHtml(t.type)}</td>
          <td>${escapeHtml(t.description)}</td>
          <td>${(t.params || []).map(p => `<code>${escapeHtml(p)}</code>`).join(', ') || '—'}</td>
        </tr>
      `).join('');

      const rules = d.system_prompt_rules.map(r => `
        <li><strong>${escapeHtml(r.letter)}.</strong> <strong>${escapeHtml(r.title)}</strong> — ${escapeHtml(r.summary)}</li>
      `).join('');

      const renderJtGroup = (label, jts) => `
        <h4>${escapeHtml(label)}</h4>
        <table class="info-table">
          <thead><tr><th>JT</th><th>Name</th><th>Propósito</th></tr></thead>
          <tbody>
            ${jts.map(j => `
              <tr>
                <td><code>${j.id}</code></td>
                <td><code>${escapeHtml(j.name)}</code></td>
                <td>${escapeHtml(j.purpose)}${j.dry_run_default ? ' <span class="badge badge--dry">dry_run=true por defecto</span>' : ''}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;

      const kb = d.knowledge_base.map(f => `
        <li><code>${escapeHtml(f.name)}</code> — ${escapeHtml(f.summary)}</li>
      `).join('');

      return `
        <div class="info-block">
          <div class="info-summary">
            <div class="info-summary__metric">
              <span class="info-summary__label">agent_name</span>
              <span class="info-summary__value"><code>${escapeHtml(d.agent_name)}</code></span>
            </div>
            <div class="info-summary__metric">
              <span class="info-summary__label">CATALOG_VERSION</span>
              <span class="info-summary__value"><code>${escapeHtml(d.catalog_version)}</code></span>
            </div>
            <div class="info-summary__metric">
              <span class="info-summary__label">Deployment</span>
              <span class="info-summary__value"><code>${escapeHtml(d.model_deployment)}</code></span>
            </div>
            <div class="info-summary__metric">
              <span class="info-summary__label">System prompt</span>
              <span class="info-summary__value">${d.instructions_chars} chars</span>
            </div>
          </div>

          <h4>Tools del agente</h4>
          <table class="info-table">
            <thead><tr><th>Tool</th><th>Tipo</th><th>Descripción</th><th>Params</th></tr></thead>
            <tbody>${tools}</tbody>
          </table>

          <h4>Reglas del system prompt (${d.system_prompt_rules.length})</h4>
          <ul class="info-list info-list--rules">${rules}</ul>

          <h4>Job Templates AWX (${d.job_templates.analysis.length + d.job_templates.diagnostic.length + d.job_templates.remediation_invasive.length})</h4>
          ${renderJtGroup('Análisis de logs (no invasivos)', d.job_templates.analysis)}
          ${renderJtGroup('Diagnóstico de infraestructura (no invasivos)', d.job_templates.diagnostic)}
          ${renderJtGroup('Remediación (invasivos, dry_run por defecto)', d.job_templates.remediation_invasive)}

          <h4>Knowledge Base disponible</h4>
          <ul class="info-list">${kb}</ul>
        </div>
      `;
    },

    renderKnowledge(d) {
      const files = d.files.map(f => `
        <li>
          <strong><code>${escapeHtml(f.filename)}</code></strong>
          <span class="info-muted">${f.lines} líneas · ${(f.size_bytes/1024).toFixed(1)} KB</span>
          <button class="ecp-btn ecp-btn--secondary info-btn-sm" data-knowledge-id="${escapeHtml(f.id)}">Ver contenido</button>
        </li>
      `).join('');

      return `
        <div class="info-block">
          <p>Archivos indexados en el vector store <code>TALENTO Knowledge Base [v7-gpt4o-guard]</code> de Foundry. El agente accede a ellos via <code>file_search</code> server-side.</p>
          <ul class="info-list info-list--files" id="knowledgeFileList">${files}</ul>
          <div class="info-knowledge-viewer" id="knowledgeViewer" style="display:none;">
            <div class="info-knowledge-viewer__header">
              <span id="knowledgeViewerTitle"></span>
              <button class="ecp-btn ecp-btn--secondary info-btn-sm" id="knowledgeViewerClose">Cerrar</button>
            </div>
            <pre class="info-knowledge-viewer__content" id="knowledgeViewerContent"></pre>
          </div>
        </div>
      `;
    },

    renderFindings(d) {
      const findings = d.findings.map(h => {
        let detail = '';
        if (h.coverage_24h) {
          const cov = h.coverage_24h.map(c => `
            <tr>
              <td><code>${escapeHtml(c.field)}</code></td>
              <td>${c.covered}/${c.total}</td>
              <td>${c.total > 0 ? Math.round(100*c.covered/c.total) : 0}%</td>
              <td>${c.ok ? '✓' : '<span class="badge badge--fail">✗</span>'}</td>
              <td>${escapeHtml(c.note || '')}</td>
            </tr>
          `).join('');
          detail += `
            <h5>Cobertura observada (24h)</h5>
            <table class="info-table">
              <thead><tr><th>Campo</th><th>Cobertura</th><th>%</th><th>OK</th><th>Nota</th></tr></thead>
              <tbody>${cov}</tbody>
            </table>
          `;
        }
        if (h.tables_status) {
          const ts = h.tables_status.map(t => `
            <tr>
              <td><code>${escapeHtml(t.table)}</code></td>
              <td>${t.rows_30d}</td>
              <td>${t.rows_30d === 0 ? '<span class="badge badge--fail">vacía</span>' : '<span class="badge badge--pass">activa</span>'}</td>
            </tr>
          `).join('');
          const avail = (h.available_tables || []).map(t => `
            <tr>
              <td><code>${escapeHtml(t.table)}</code></td>
              <td>${t.rows_7d.toLocaleString()}</td>
              <td>${escapeHtml(t.note)}</td>
            </tr>
          `).join('');
          detail += `
            <h5>Tablas Application Insights (vacías 30d)</h5>
            <table class="info-table">
              <thead><tr><th>Tabla</th><th>Rows 30d</th><th>Estado</th></tr></thead>
              <tbody>${ts}</tbody>
            </table>
            <h5>Lo que SÍ tenemos en el workspace</h5>
            <table class="info-table">
              <thead><tr><th>Tabla</th><th>Rows 7d</th><th>Nota</th></tr></thead>
              <tbody>${avail}</tbody>
            </table>
          `;
        }
        const missing = (h.missing_capabilities || []).map(m => `<li>${escapeHtml(m)}</li>`).join('');
        const pendingActionHtml = h.pending_action
          ? `<div class="info-finding__pending"><strong>⏳ Pendiente:</strong> ${escapeHtml(h.pending_action)}</div>`
          : '';
        return `
          <article class="info-finding info-finding--${escapeHtml(h.severity)}">
            <header class="info-finding__header">
              <span class="badge badge--${escapeHtml(h.severity)}">${escapeHtml(h.severity.toUpperCase())}</span>
              <h4>${escapeHtml(h.title)}</h4>
            </header>
            <p>${escapeHtml(h.summary)}</p>
            ${detail}
            ${missing ? `<h5>Capacidades perdidas mientras no se resuelva</h5><ul class="info-list">${missing}</ul>` : ''}
            ${pendingActionHtml}
            <div class="info-finding__request">
              <strong>Solicitud al equipo de plataforma:</strong> ${escapeHtml(h.request_to_eapps)}
            </div>
          </article>
        `;
      }).join('');

      const works = d.what_works_today.map(w => `<li>${escapeHtml(w)}</li>`).join('');

      return `
        <div class="info-block">
          <p><span class="badge badge--warn">${escapeHtml(d.status)}</span></p>
          ${findings}
          <h4>Lo que el agente SÍ puede hacer hoy (con datos disponibles)</h4>
          <ul class="info-list">${works}</ul>
        </div>
      `;
    },

    renderRuns(d) {
      if (!d.runs || d.runs.length === 0) {
        return `<div class="info-block"><p>No hay runs históricos disponibles.</p></div>`;
      }
      const rows = d.runs.map(r => {
        const cats = ['happy','ambiguous','destructive','multi_turn'];
        const byCat = cats.map(c => {
          const b = r.by_category[c];
          if (!b) return '<td>—</td>';
          const rate = b.n > 0 ? Math.round(100*b.verdict/b.n) : 0;
          return `<td>${b.verdict}/${b.n} (${rate}%)</td>`;
        }).join('');
        const elapsed = r.elapsed_seconds ? `${(r.elapsed_seconds/60).toFixed(1)} min` : '—';
        return `
          <tr>
            <td><code>${escapeHtml(r.timestamp)}</code></td>
            <td>${r.total_cases}</td>
            ${byCat}
            <td>${escapeHtml(elapsed)}</td>
          </tr>
        `;
      }).join('');

      return `
        <div class="info-block">
          <p>Últimos ${d.runs.length} runs de evaluación. Pass rate por categoría (verdict global).</p>
          <table class="info-table info-table--compact">
            <thead>
              <tr>
                <th>Timestamp</th><th>Total</th>
                <th>Happy</th><th>Ambiguous</th><th>Destructive</th><th>Multi-turn</th>
                <th>Duración</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      `;
    },
  };

  // Lazy-load handler para click en "Ver contenido" de knowledge files
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-knowledge-id]');
    if (btn) {
      const fid = btn.dataset.knowledgeId;
      const viewer = document.getElementById('knowledgeViewer');
      const title = document.getElementById('knowledgeViewerTitle');
      const content = document.getElementById('knowledgeViewerContent');
      if (!viewer || !title || !content) return;
      title.textContent = `Cargando ${fid}...`;
      viewer.style.display = 'block';
      content.textContent = '';
      try {
        const resp = await fetch(`/api/info/knowledge/${encodeURIComponent(fid)}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        title.textContent = data.filename;
        // Render Markdown si marked.js esta disponible
        if (window.marked) {
          content.innerHTML = marked.parse(data.content);
        } else {
          content.textContent = data.content;
        }
      } catch (err) {
        content.textContent = `Error: ${err.message}`;
      }
    }
    if (e.target.id === 'knowledgeViewerClose') {
      document.getElementById('knowledgeViewer').style.display = 'none';
    }
  });

})();
