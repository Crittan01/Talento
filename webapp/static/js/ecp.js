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
  };

  const el = {
    cards: document.getElementById('cardsGrid'),
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
    filterThreshold: document.getElementById('filterThreshold'),
    filterThresholdGroup: document.getElementById('filterThresholdGroup'),
    filterHint: document.getElementById('filterHint'),
    connStatus: document.getElementById('connStatus'),
  };

  // -------------------------------------------------------------------------
  // Filter bar — gestiona valores actuales y visibilidad del threshold
  // -------------------------------------------------------------------------
  function readFilters() {
    return {
      time_range_hours: parseInt(el.filterTimeRange.value, 10),
      failed_threshold: parseInt(el.filterThreshold.value, 10),
    };
  }
  function updateFilterHint() {
    const f = readFilters();
    el.filterHint.textContent =
      `Filtros activos: ${f.time_range_hours}h` +
      (el.filterThresholdGroup.hidden ? '' : ` · umbral ${f.failed_threshold}`);
  }
  [el.filterTimeRange, el.filterThreshold].forEach(s => {
    s.addEventListener('change', () => {
      markCardsAsUsingFilters();
      updateFilterHint();
    });
  });

  function markCardsAsUsingFilters() {
    const f = readFilters();
    const isDefault = f.time_range_hours === 24 && f.failed_threshold === 5;
    el.cards.querySelectorAll('.ecp-sidebar-card').forEach(c => {
      const accepts = (c.dataset.acceptsFilters || '').split(',').filter(Boolean);
      c.dataset.filterActive = (!isDefault && accepts.length > 0) ? 'true' : 'false';
    });
  }
  // Inicial
  updateFilterHint();
  markCardsAsUsingFilters();

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
  el.cards.addEventListener('click', (e) => {
    const card = e.target.closest('.ecp-sidebar-card');
    if (!card) return;
    if (card.classList.contains('is-running')) return; // ya activa

    const sid = card.dataset.scenarioId;
    const renderer = card.dataset.renderer;
    const freeText = card.dataset.freeText === 'true';

    // Determinar qué filtros aplican a esta card
    const acceptsFilters = (card.dataset.acceptsFilters || '').split(',').filter(Boolean);
    const allFilters = readFilters();
    const filters = {};
    acceptsFilters.forEach(f => {
      if (allFilters[f] != null) filters[f] = allFilters[f];
    });

    if (freeText) {
      openFreeTextModal(card, sid, renderer);
    } else {
      runScenario(card, sid, renderer, null, filters);
    }
  });

  el.panelClose.addEventListener('click', closePanel);

  // -------------------------------------------------------------------------
  // Free-text modal
  // -------------------------------------------------------------------------
  function openFreeTextModal(card, sid, renderer) {
    el.modalInput.value = '';
    el.modal.classList.add('is-open');
    el.modalInput.focus();
    state._pendingCard = card;
    state._pendingSid = sid;
    state._pendingRenderer = renderer;
  }
  function closeFreeTextModal() {
    el.modal.classList.remove('is-open');
    state._pendingCard = null;
  }
  el.modalCancel.addEventListener('click', closeFreeTextModal);
  el.modalCancelX.addEventListener('click', closeFreeTextModal);
  el.modalRun.addEventListener('click', () => {
    const txt = el.modalInput.value.trim();
    if (!txt) {
      alert('Escribe una pregunta primero.');
      el.modalInput.focus();
      return;
    }
    closeFreeTextModal();
    runScenario(state._pendingCard, state._pendingSid, state._pendingRenderer, txt, {});
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

    // Cambiar layout: ocultar welcome, mostrar run banner + timeline
    el.welcome.style.display = 'none';
    el.runBanner.style.display = 'flex';
    el.timelineWrap.style.display = 'block';
    el.resultWrap.style.display = 'none'; // se muestra cuando llega agent.final

    // Poblar banner
    const cardIcon = card.querySelector('.ecp-sidebar-card__icon').textContent;
    const cardTitle = card.querySelector('.ecp-sidebar-card__title').textContent;
    el.runBannerIcon.textContent = cardIcon;
    el.runBannerTitle.textContent = cardTitle;

    // Badge de filtros aplicados (solo si difieren de defaults)
    const filterStr = formatFiltersBadge(filters);
    if (filterStr) {
      el.filtersBadge.textContent = filterStr;
      el.filtersBadge.style.display = 'inline-block';
    } else {
      el.filtersBadge.style.display = 'none';
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
      const niceArgs = evt.tool === 'query_log_analytics'
        ? `<code>${escapeHtml(String(evt.args.query || '').slice(0, 200))}</code>`
        : `template_id=<code>${evt.args.template_id}</code>`;
      appendTimeline('kql', '🛠️', `Tool <strong>${evt.tool}</strong> → ${niceArgs}`);
    }
    else if (t === 'tool.kql.done') {
      appendTimeline('kql', '✓', `KQL OK (${evt.elapsed_seconds}s) — ${evt.rows} filas`);
    }
    else if (t === 'tool.kql.error') {
      appendTimeline('error', '⚠️', `KQL ERROR (${evt.elapsed_seconds}s) — ${escapeHtml(evt.error || '')}`);
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
      appendTimeline('final', '🤖', `Síntesis final lista (${evt.elapsed_seconds}s total).`);
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
        <div class="ecp-agent-reply__header">🤖 RESPUESTA DEL AGENTE</div>
        ${agentHtml}
      </div>
    `;
    // Mostrar el wrapper del resultado (estaba oculto hasta agent.final)
    el.resultWrap.style.display = 'block';
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
    // Volver al estado de bienvenida (el layout permanece estable)
    el.runBanner.style.display = 'none';
    el.timelineWrap.style.display = 'none';
    el.resultWrap.style.display = 'none';
    el.welcome.style.display = 'block';
    el.timeline.innerHTML = '';
    el.result.innerHTML = '';
    el.filtersBadge.style.display = 'none';
    state.activeCard = null;
  }

  function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

})();
