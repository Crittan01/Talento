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
    main: document.getElementById('mainLayout'),
    panel: document.getElementById('panel'),
    panelTitle: document.getElementById('panelTitle'),
    panelElapsed: document.getElementById('panelElapsed'),
    panelClose: document.getElementById('panelClose'),
    timeline: document.getElementById('timeline'),
    result: document.getElementById('result'),
    modal: document.getElementById('freeTextModal'),
    modalInput: document.getElementById('freeTextInput'),
    modalRun: document.getElementById('freeTextRunBtn'),
    modalCancel: document.getElementById('freeTextCancelBtn'),
    modalCancelX: document.getElementById('freeTextCancel'),
  };

  // -------------------------------------------------------------------------
  // Card click handler
  // -------------------------------------------------------------------------
  el.cards.addEventListener('click', (e) => {
    const card = e.target.closest('.ecp-card');
    if (!card) return;
    if (card.classList.contains('is-running')) return; // ya activa

    const sid = card.dataset.scenarioId;
    const renderer = card.dataset.renderer;
    const freeText = card.dataset.freeText === 'true';

    if (freeText) {
      openFreeTextModal(card, sid, renderer);
    } else {
      runScenario(card, sid, renderer, null);
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
    runScenario(state._pendingCard, state._pendingSid, state._pendingRenderer, txt);
  });

  // -------------------------------------------------------------------------
  // Run scenario
  // -------------------------------------------------------------------------
  async function runScenario(card, scenarioId, renderer, freeText) {
    if (state.activeRunId) {
      alert('Hay un escenario en ejecución. Espera a que termine o cierra el panel.');
      return;
    }

    card.classList.add('is-running');
    state.activeCard = card;
    state.activeRenderer = renderer;
    state.awxUrl = null;
    state.artifacts = {};

    // Abrir panel
    el.main.classList.remove('ecp-main--no-panel');
    el.panel.style.display = 'flex';
    el.panelTitle.textContent = card.querySelector('.ecp-card__title').textContent;
    el.timeline.innerHTML = '';
    el.result.innerHTML = '<div class="ecp-result__empty">Esperando primer evento del agente…</div>';

    state.startTime = Date.now();
    startElapsedTimer();

    let resp;
    try {
      resp = await fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario_id: scenarioId,
          free_text: freeText,
          mock: state.forceMockUrlParam,
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
    const text = `AWX polling — job <code>${evt.job_id}</code> status=<strong>${evt.status}</strong> (${evt.elapsed_seconds}s)`;
    if (pollNode) {
      pollNode.querySelector('.ecp-timeline__text').innerHTML = text;
    } else {
      const node = renderTimelineItem('awx', '⏳', text);
      node.classList.add(`poll-${evt.job_id}`);
      el.timeline.appendChild(node);
      autoscrollTimeline();
    }
  }

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
    el.result.innerHTML = resultHtml + `
      <div class="ecp-agent-reply">
        <div class="ecp-agent-reply__header">🤖 RESPUESTA DEL AGENTE</div>
        ${escapeHtml(finalText)}
      </div>
    `;
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
    el.panel.style.display = 'none';
    el.main.classList.add('ecp-main--no-panel');
    state.activeCard = null;
  }

  function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

})();
