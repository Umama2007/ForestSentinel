document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const tabFire = document.getElementById('tab-fire');
  const tabConservation = document.getElementById('tab-conservation');
  const mapFrame = document.getElementById('map-frame');
  const openNewTabBtn = document.getElementById('open-map-new-tab');
  const fullscreenBtn = document.getElementById('toggle-fullscreen');
  const mapContainer = document.getElementById('map-container');
  
  const modal = document.getElementById('image-modal');
  const modalImg = document.getElementById('modal-img');
  const modalClose = document.getElementById('modal-close');
  
  const terminal = document.getElementById('terminal-output');
  const clearTerminalBtn = document.getElementById('clear-terminal');
  
  let currentMap = 'fire';

  // Map Switching
  function switchMap(type) {
    currentMap = type;
    if (type === 'fire') {
      tabFire.classList.add('active');
      tabConservation.classList.remove('active');
      mapFrame.src = '/map/fire';
      openNewTabBtn.href = '/map/fire';
    } else {
      tabConservation.classList.add('active');
      tabFire.classList.remove('active');
      mapFrame.src = '/map/conservation';
      openNewTabBtn.href = '/map/conservation';
    }
  }

  if (tabFire && tabConservation) {
    tabFire.addEventListener('click', () => switchMap('fire'));
    tabConservation.addEventListener('click', () => switchMap('conservation'));
  }

  // Fullscreen Map
  if (fullscreenBtn && mapContainer) {
    fullscreenBtn.addEventListener('click', () => {
      if (!document.fullscreenElement) {
        mapContainer.requestFullscreen().catch(err => {
          console.error(`Error attempting to enable fullscreen: ${err.message}`);
        });
      } else {
        document.exitFullscreen();
      }
    });
  }

  // Image Modal
  document.querySelectorAll('.chart-card-body img').forEach(img => {
    img.addEventListener('click', () => {
      modalImg.src = img.src;
      modal.classList.add('active');
    });
  });

  if (modalClose) {
    modalClose.addEventListener('click', () => modal.classList.remove('active'));
  }

  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.classList.remove('active');
    });
  }

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modal && modal.classList.contains('active')) {
      modal.classList.remove('active');
    }
  });

  // Terminal logging helper
  function logTerminal(message, type = 'info') {
    const timestamp = new Date().toLocaleTimeString();
    let prefix = `[${timestamp}] `;
    if (type === 'error') prefix += '❌ ERROR: ';
    else if (type === 'success') prefix += '✅ SUCCESS: ';
    else prefix += 'ℹ️ ';

    terminal.textContent += `\n${prefix}${message}`;
    terminal.scrollTop = terminal.scrollHeight;
  }

  if (clearTerminalBtn) {
    clearTerminalBtn.addEventListener('click', () => {
      terminal.textContent = 'ForestSentinel v1.0.0 Console Ready. Select an action to execute.';
    });
  }

  // Pipeline Run Triggers
  window.triggerPipeline = async function(stage) {
    logTerminal(`Initiating pipeline execution: ${stage.toUpperCase()}...`);
    try {
      const response = await fetch(`/api/run/${stage}`, { method: 'POST' });
      const data = await response.json();
      
      if (response.ok) {
        logTerminal(`Pipeline output: \n${data.output || data.message}`, 'success');
        if (data.map_updated) {
          logTerminal('Reloading interactive maps with refreshed analysis data...', 'info');
          mapFrame.src = currentMap === 'fire' ? '/map/fire?t=' + Date.now() : '/map/conservation?t=' + Date.now();
        }
      } else {
        logTerminal(`Pipeline execution failed: ${data.error || data.message}`, 'error');
      }
    } catch (err) {
      logTerminal(`Network / Server error: ${err.message}`, 'error');
    }
  };

  // Initial verification fetch
  fetch('/api/metrics')
    .then(r => r.json())
    .then(metrics => {
      if (metrics.status === 'ok') {
        logTerminal(`System initialized. Connected to Firestore project: ${metrics.firestore_project_id}`);
        logTerminal(`Loaded ${metrics.fire_detections} fire records across ${metrics.populated_grid_cells} grid cells.`);
        logTerminal(`Conservation layer: ${metrics.species_summaries} species summaries (${metrics.species_status}).`);
      }
    })
    .catch(err => {
      console.warn('Metrics check:', err);
    });
});
