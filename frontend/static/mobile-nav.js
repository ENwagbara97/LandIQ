/* =================================================================
   LANDIQ MOBILE/TABLET RESPONSIVE INTERACTION SCRIPT
   ================================================================= */

document.addEventListener('DOMContentLoaded', () => {
  // Initialize Lucide Icons
  if (window.lucide) {
    lucide.createIcons();
  }

  // --- Theme Syncing and Initialization ---
  const syncSegmentedControl = () => {
    const activeTheme = document.documentElement.classList.contains('theme-light') ? 'light' : 'dark';
    const segmentButtons = document.querySelectorAll('#settings-theme-toggle .segment-btn');
    segmentButtons.forEach(btn => {
      if (btn.getAttribute('data-theme') === activeTheme) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    // Also sync standard desktop toggle icons if present
    const icon = document.getElementById('theme-icon');
    if (icon) {
      icon.className = activeTheme === 'light' ? 'fa-solid fa-moon' : 'fa-solid fa-sun';
    }
  };

  syncSegmentedControl();

  // Wire Segmented theme button switches in settings
  document.querySelectorAll('#settings-theme-toggle .segment-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const selectedTheme = e.currentTarget.getAttribute('data-theme');
      const hasLight = document.documentElement.classList.contains('theme-light');
      
      if (selectedTheme === 'light' && !hasLight) {
        // Toggle theme to light
        if (typeof window.toggleTheme === 'function') {
          window.toggleTheme();
        } else {
          document.documentElement.classList.add('theme-light');
          localStorage.setItem('landiq-theme', 'light');
        }
      } else if (selectedTheme === 'dark' && hasLight) {
        // Toggle theme to dark
        if (typeof window.toggleTheme === 'function') {
          window.toggleTheme();
        } else {
          document.documentElement.classList.remove('theme-light');
          localStorage.setItem('landiq-theme', 'dark');
        }
      }
      syncSegmentedControl();
      showToast(`Theme switched to ${selectedTheme.toUpperCase()}`);
    });
  });

  // --- Mobile Tab Navigation Controls ---
  const tabButtons = document.querySelectorAll('.mobile-tab-btn');
  const switchTab = (tabId) => {
    document.body.setAttribute('data-active-tab', tabId);
    tabButtons.forEach(btn => {
      if (btn.getAttribute('data-tab') === tabId) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    // Refresh map layout sizes to prevent Leaflet gray tiling issues
    setTimeout(() => {
      if (typeof window.welcomeMapInstance !== 'undefined' && window.welcomeMapInstance) {
        window.welcomeMapInstance.invalidateSize();
      }
      if (typeof window.gateMapInstance !== 'undefined' && window.gateMapInstance) {
        window.gateMapInstance.invalidateSize();
      }
      if (typeof window.reportMapInstance !== 'undefined' && window.reportMapInstance) {
        window.reportMapInstance.invalidateSize();
      }
    }, 150);
  };

  tabButtons.forEach(btn => {
    btn.addEventListener('click', (e) => {
      const tabId = e.currentTarget.getAttribute('data-tab');
      switchTab(tabId);
    });
  });

  // Expose switchTab globally for deep links / programmatic redirects
  window.switchMobileTab = switchTab;

  // --- Hamburger Side Drawer Panel Toggles ---
  const hamburgerBtn = document.getElementById('btn-hamburger');
  const avatarBtn = document.getElementById('mobile-profile-avatar');
  const drawerOverlay = document.getElementById('hamburger-drawer');
  const closeDrawerBtn = document.getElementById('btn-close-drawer');

  const openDrawer = () => {
    if (drawerOverlay) drawerOverlay.classList.add('active');
  };

  const closeDrawer = () => {
    if (drawerOverlay) drawerOverlay.classList.remove('active');
  };

  if (hamburgerBtn) hamburgerBtn.addEventListener('click', openDrawer);
  if (avatarBtn) avatarBtn.addEventListener('click', openDrawer);
  if (closeDrawerBtn) closeDrawerBtn.addEventListener('click', closeDrawer);
  
  if (drawerOverlay) {
    drawerOverlay.addEventListener('click', (e) => {
      if (e.target === drawerOverlay) {
        closeDrawer();
      }
    });
  }

  // --- Settings and Legal Modals Control ---
  const settingsModal = document.getElementById('custom-settings-modal');
  const settingsDrawerItem = document.getElementById('drawer-item-settings');
  const closeSettingsBtn = document.getElementById('btn-close-settings');
  const desktopSettingsBtn = document.getElementById('btn-settings'); // Desktop Settings button integration

  const openSettings = () => {
    closeDrawer();
    if (settingsModal) settingsModal.style.display = 'flex';
  };

  const closeSettings = () => {
    if (settingsModal) settingsModal.style.display = 'none';
  };

  if (settingsDrawerItem) settingsDrawerItem.addEventListener('click', openSettings);
  if (desktopSettingsBtn) desktopSettingsBtn.addEventListener('click', openSettings);
  if (closeSettingsBtn) closeSettingsBtn.addEventListener('click', closeSettings);

  // Link inside Drawer that directs to History
  const historyDrawerItem = document.getElementById('drawer-item-history');
  if (historyDrawerItem) {
    historyDrawerItem.addEventListener('click', () => {
      closeDrawer();
      switchTab('history');
    });
  }

  // Floating Action Button (+) on mobile history screen
  const historyFab = document.getElementById('mobile-history-fab');
  if (historyFab) {
    historyFab.addEventListener('click', () => {
      switchTab('analyse');
    });
  }

  // --- Legal / Policy Dialogs Helper ---
  const policyModal = document.getElementById('custom-policy-modal');
  const policyTitle = document.getElementById('policy-modal-title');
  const policyBody = document.getElementById('policy-modal-body');
  const closePolicyBtn = document.getElementById('btn-close-policy');

  const showLegal = (title, text) => {
    if (policyTitle) policyTitle.innerText = title;
    if (policyBody) policyBody.innerHTML = text;
    if (policyModal) policyModal.style.display = 'flex';
  };

  const closeLegal = () => {
    if (policyModal) policyModal.style.display = 'none';
  };

  if (closePolicyBtn) closePolicyBtn.addEventListener('click', closeLegal);

  // Privacy Policy trigger links
  const privacyText = `
    <h4>Privacy Policy</h4>
    <p>Last updated: June 2026</p>
    <p>This privacy policy describes how LandIQ manages user data. The system is designed to run locally, meaning all your sensitive cadastral records, area files, coordinates, and report parameters are kept within your browser's local storage and the local system databases.</p>
    <p><strong>1. Data Containment</strong></p>
    <p>LandIQ does not collect personal identifiers or upload survey vectors to third-party databases. All geographical comparisons are executed securely on local relational servers.</p>
    <p><strong>2. Browser Cache & Storage</strong></p>
    <p>Clearing your browser's site cookies or application data cache will wipe your active history logs. Please ensure you export reports to PDF to preserve them.</p>
  `;

  const termsText = `
    <h4>Terms of Service</h4>
    <p>Last updated: June 2026</p>
    <p>By using the LandIQ Spatial screening tool, you agree to these operational terms:</p>
    <p><strong>1. Local System Runtime</strong></p>
    <p>This runtime is configured as a precision GIS validation tool. The analysis, elevation profiles, and flood-risk boundaries mapped here are local fallbacks and simulations.</p>
    <p><strong>2. No Legal Surveyor representation</strong></p>
    <p>LandIQ reports are advisory guidelines and screening checkpoints only. They do not represent final legal land surveys or government-approved boundary gazettes. Final deeds must be verified at the appropriate State Land Registry.</p>
  `;

  const showPrivacy = (e) => {
    if (e) e.preventDefault();
    closeDrawer();
    closeSettings();
    showLegal("Privacy Policy", privacyText);
  };

  const showTerms = (e) => {
    if (e) e.preventDefault();
    closeDrawer();
    closeSettings();
    showLegal("Terms of Service", termsText);
  };

  // Wire policy triggers
  const drawerPolicyLink = document.getElementById('drawer-link-policy');
  const drawerTermsLink = document.getElementById('drawer-link-terms');
  const settingsPolicyBtn = document.getElementById('btn-policy-row');
  const settingsTermsBtn = document.getElementById('btn-terms-row');
  const drawerPolicyBtn = document.getElementById('drawer-btn-policy'); // old button compatibility

  if (drawerPolicyLink) drawerPolicyLink.addEventListener('click', showPrivacy);
  if (drawerTermsLink) drawerTermsLink.addEventListener('click', showTerms);
  if (settingsPolicyBtn) settingsPolicyBtn.addEventListener('click', showPrivacy);
  if (settingsTermsBtn) settingsTermsBtn.addEventListener('click', showTerms);
  if (drawerPolicyBtn) drawerPolicyBtn.addEventListener('click', showPrivacy);

  // Other menu item placeholders (Help, Feedback)
  const showPlaceholderHelp = () => {
    closeDrawer();
    closeSettings();
    alert("Help Center: For support, please contact help@landiq.ng or reference our user guides.");
  };

  const showPlaceholderFeedback = () => {
    closeDrawer();
    closeSettings();
    const fb = prompt("Send Feedback:\nWe would love to hear your thoughts. Enter your feedback below:");
    if (fb) {
      showToast("Thank you for your feedback!");
    }
  };

  const drawerHelpItem = document.getElementById('drawer-item-help');
  const drawerFeedbackItem = document.getElementById('drawer-item-feedback');
  const settingsHelpBtn = document.getElementById('btn-help-row');
  const settingsFeedbackBtn = document.getElementById('btn-feedback-row');

  if (drawerHelpItem) drawerHelpItem.addEventListener('click', showPlaceholderHelp);
  if (drawerFeedbackItem) drawerFeedbackItem.addEventListener('click', showPlaceholderFeedback);
  if (settingsHelpBtn) settingsHelpBtn.addEventListener('click', showPlaceholderHelp);
  if (settingsFeedbackBtn) settingsFeedbackBtn.addEventListener('click', showPlaceholderFeedback);

  // --- Toast Toaster Snackbar queue manager ---
  window.showToast = (message) => {
    const container = document.getElementById('snackbar-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = 'snackbar-toast';
    toast.innerHTML = `
      <i data-lucide="check"></i>
      <span>${message}</span>
    `;
    
    // Clear previous toasts to follow "max one toast visible" constraint
    container.innerHTML = '';
    container.appendChild(toast);
    
    if (window.lucide) {
      lucide.createIcons();
    }

    // Fade out and remove toast after 3 seconds
    setTimeout(() => {
      toast.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(12px)';
      setTimeout(() => {
        if (toast.parentNode === container) {
          container.removeChild(toast);
        }
      }, 500);
    }, 3000);
  };

  // --- Auto-switch tabs on successful pipeline upload ---
  const formElement = document.getElementById('upload-form');
  if (formElement) {
    formElement.addEventListener('submit', () => {
      // Switch active tab to map to show the progress loading screen
      const currentWidth = window.innerWidth;
      if (currentWidth <= 767) {
        switchTab('map');
      }
    });
  }

  // Set up observers to look for active results and switch to Report tab
  const badgeMethodLabel = document.getElementById('badge-method-label');
  if (badgeMethodLabel) {
    const observer = new MutationObserver(() => {
      const currentWidth = window.innerWidth;
      if (currentWidth <= 767) {
        showToast("Boundary extraction successful!");
        switchTab('report');
      }
    });
    observer.observe(badgeMethodLabel, { childList: true });
  }

  // --- Drag-to-Dismiss / Drag-down bottom sheet ---
  const sheet = document.querySelector('.sidebar > .card:first-child');
  const handle = document.getElementById('mobile-drag-handle');
  if (sheet && handle) {
    let startY = 0;
    let currentY = 0;
    let isDragging = false;

    handle.addEventListener('touchstart', (e) => {
      startY = e.touches[0].clientY;
      isDragging = true;
      sheet.style.transition = 'none'; // Disable animations during drag
    });

    handle.addEventListener('touchmove', (e) => {
      if (!isDragging) return;
      currentY = e.touches[0].clientY;
      const deltaY = currentY - startY;
      
      // Only allow dragging downwards
      if (deltaY > 0) {
        sheet.style.transform = `translateY(${deltaY}px)`;
      }
    });

    handle.addEventListener('touchend', (e) => {
      if (!isDragging) return;
      isDragging = false;
      sheet.style.transition = 'transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)';
      
      const deltaY = currentY - startY;
      // If dragged down more than 150px, collapse sheet by switching to Map tab
      if (deltaY > 150) {
        sheet.style.transform = 'translateY(100%)';
        setTimeout(() => {
          sheet.style.transform = '';
          switchTab('map');
        }, 300);
      } else {
        // Reset sheet to normal position
        sheet.style.transform = '';
      }
    });
  }

  // --- Mobile Report Mode Toggle Sync ---
  const mobileSegmentBtns = document.querySelectorAll('.mobile-segmented-control .segment-btn');
  const desktopModeCheckbox = document.getElementById('report-mode-toggle');
  
  if (mobileSegmentBtns.length > 0 && desktopModeCheckbox) {
    mobileSegmentBtns.forEach(btn => {
      btn.addEventListener('click', (e) => {
        // Update visual active state
        mobileSegmentBtns.forEach(b => b.classList.remove('active'));
        e.currentTarget.classList.add('active');
        
        // Sync to desktop checkbox
        const mode = e.currentTarget.getAttribute('data-mode');
        const isExpert = (mode === 'expert');
        if (desktopModeCheckbox.checked !== isExpert) {
          desktopModeCheckbox.checked = isExpert;
          desktopModeCheckbox.dispatchEvent(new Event('change'));
        }
      });
    });

    // Also listen to desktop checkbox changes to keep mobile in sync
    desktopModeCheckbox.addEventListener('change', (e) => {
      const mode = e.target.checked ? 'expert' : 'simple';
      mobileSegmentBtns.forEach(b => {
        if (b.getAttribute('data-mode') === mode) {
          b.classList.add('active');
        } else {
          b.classList.remove('active');
        }
      });
    });
  }
});
