const state = {
  projects: [],
  selectedProject: null,
  adminProjectOpen: false,
  activeView: "admin",
  operatorWorkspaceOpen: false,
  operatorPreviewImage: null,
  activeProjectTab: "summary",
  operatorActiveStepId: null,
  adminPreviewStepId: null,
  adminPreviewSearch: "",
  adminPreviewView: defaultAdminPreviewView(),
  selectedLineIds: new Set(),
  proEditorStepId: null,
  imageViews: new Map(),
  calibrationDesignators: new Map(),
  calibrationDrafts: new Map(),
  polarityEditDesignator: null,
  operatorView: loadOperatorViewState(),
  pinIndexes: [],
};

const OPERATOR_AUTO_FIT_MIN_ZOOM = 18;

const els = {
  views: {
    admin: document.getElementById("adminView"),
    operator: document.getElementById("operatorView"),
  },
  navButtons: Array.from(document.querySelectorAll("[data-view]")),
  panelButtons: Array.from(document.querySelectorAll("[data-panel]")),
  closePanelButtons: Array.from(document.querySelectorAll("[data-close-panel]")),
  actionPanels: Array.from(document.querySelectorAll("[data-action-panel]")),
  importForm: document.getElementById("importForm"),
  importSummary: document.getElementById("importSummary"),
  projectForm: document.getElementById("projectForm"),
  editProjectForm: document.getElementById("editProjectForm"),
  boardImageForm: document.getElementById("boardImageForm"),
  previewImagesForm: document.getElementById("previewImagesForm"),
  reimportForm: document.getElementById("reimportForm"),
  reimportSummary: document.getElementById("reimportSummary"),
  supplementPointsForm: document.getElementById("supplementPointsForm"),
  supplementPointsSummary: document.getElementById("supplementPointsSummary"),
  pinIndexForm: document.getElementById("pinIndexForm"),
  pinIndexList: document.getElementById("pinIndexList"),
  stepForm: document.getElementById("stepForm"),
  operatorProjectSearch: document.getElementById("operatorProjectSearch"),
  operatorProjectList: document.getElementById("operatorProjectList"),
  operatorProjectBrowser: document.getElementById("operatorProjectBrowser"),
  operatorWorkspace: document.getElementById("operatorWorkspace"),
  operatorHeaderProject: document.getElementById("operatorHeaderProject"),
  projectSearch: document.getElementById("projectSearch"),
  projectTableBody: document.getElementById("projectTableBody"),
  projectDetails: document.getElementById("projectDetails"),
  adminPageTitle: document.getElementById("adminPageTitle"),
  adminPageSubtitle: document.getElementById("adminPageSubtitle"),
  adminProjectListPanel: document.getElementById("adminProjectListPanel"),
  adminActionPanels: document.getElementById("adminActionPanels"),
  adminListActions: Array.from(document.querySelectorAll("[data-admin-list-action]")),
  adminDetailActions: Array.from(document.querySelectorAll("[data-admin-detail-action]")),
  backToProjects: document.getElementById("backToProjects"),
  operatorSteps: document.getElementById("operatorSteps"),
  refreshProjects: document.getElementById("refreshProjects"),
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Błąd API");
  }
  return payload;
}

async function apiForm(path, formData) {
  const response = await fetch(path, {
    method: "POST",
    body: formData,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Błąd importu");
  }
  return payload;
}

function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function normalizeStaticLabels() {
  const form = els.previewImagesForm;
  if (!form) {
    return;
  }
  const title = form.querySelector("h2");
  const description = form.querySelector(".panel-head p");
  const thtLabel = form.querySelector('input[name="thtPreviewImage"]')?.closest("label");
  const labelingLabel = form.querySelector('input[name="labelingPreviewImage"]')?.closest("label");
  const submit = form.querySelector('button[type="submit"]');
  const hint = form.querySelector(".form-row .muted");

  if (title) {
    title.textContent = "Podgl\u0105dy operatora";
  }
  if (description) {
    description.textContent = "Osobne zdj\u0119cia pomocnicze dla monta\u017cu THT i oklejania";
  }
  if (thtLabel) {
    thtLabel.childNodes[0].textContent = "\n                                Podgl\u0105d THT\n                                ";
  }
  if (labelingLabel) {
    labelingLabel.childNodes[0].textContent = "\n                                Podgl\u0105d Oklejanie\n                                ";
  }
  if (submit) {
    submit.textContent = "Zapisz podgl\u0105dy";
  }
  if (hint) {
    hint.textContent = "Mo\u017cesz podmieni\u0107 tylko jedno zdj\u0119cie, drugie zostanie bez zmian.";
  }
}

function normalizeMedcomIndex(value) {
  return String(value || "").replace(/\s+/g, "").toUpperCase();
}

function pinIndexSet() {
  return new Set(state.pinIndexes.map((item) => normalizeMedcomIndex(item.medcom_index)));
}

function defaultOperatorViewState() {
  return {
    zoom: 100,
    markerSize: 100,
    rotation: 0,
    markerPalette: "contrast",
    showAllPoints: false,
    showLabels: true,
    showPolarity: false,
    showContours: false,
    focusMode: false,
  };
}

function defaultAdminPreviewView() {
  return {
    zoom: 100,
    rotation: 0,
    markerPalette: "contrast",
    showAllPoints: false,
    showLabels: true,
    showPolarity: false,
    showContours: true,
  };
}

function clampOperatorZoom(value) {
  const zoom = Number(value);
  return Math.round(Math.max(35, Math.min(240, Number.isFinite(zoom) ? zoom : 100)));
}

function clampMarkerSize(value) {
  const size = Number(value);
  return Math.round(Math.max(75, Math.min(180, Number.isFinite(size) ? size : 100)));
}

function operatorMarkerSizeForZoom(zoomPercent, markerSizePercent = 100) {
  const zoom = Number.isFinite(Number(zoomPercent)) ? Number(zoomPercent) : 100;
  const markerScale = Math.max(0.85, Math.min(1.6, 0.85 + (zoom - 60) / 150));
  const userScale = clampMarkerSize(markerSizePercent) / 100;
  return Math.round(Math.max(13, Math.min(44, 17 * markerScale * userScale)));
}

function normalizeViewRotation(value) {
  const rotation = Number(value);
  return [0, 90, 180, 270].includes(rotation) ? rotation : 0;
}

function normalizeMarkerPalette(value) {
  return ["contrast", "magenta", "cyan", "amber"].includes(value) ? value : "contrast";
}

function normalizeOperatorViewState(view = {}) {
  const defaults = defaultOperatorViewState();
  return {
    zoom: clampOperatorZoom(view.zoom || defaults.zoom),
    markerSize: clampMarkerSize(view.markerSize || defaults.markerSize),
    rotation: normalizeViewRotation(view.rotation),
    markerPalette: normalizeMarkerPalette(view.markerPalette),
    showAllPoints: false,
    showLabels: view.showLabels !== false,
    showPolarity: Boolean(view.showPolarity),
    showContours: Boolean(view.showContours),
    focusMode: Boolean(view.focusMode),
  };
}

function loadOperatorViewState() {
  try {
    return normalizeOperatorViewState(JSON.parse(localStorage.getItem("inserterOperatorView") || "{}"));
  } catch (error) {
    return defaultOperatorViewState();
  }
}

function saveOperatorViewState() {
  localStorage.setItem("inserterOperatorView", JSON.stringify(state.operatorView));
}

function updateOperatorView(patch) {
  state.operatorView = normalizeOperatorViewState({
    ...state.operatorView,
    ...patch,
  });
  saveOperatorViewState();
  renderOperatorSteps();
}

function setView(viewName) {
  const previousView = state.activeView;
  state.activeView = viewName;
  if (viewName === "operator" && previousView !== "operator") {
    state.operatorWorkspaceOpen = false;
  }
  els.navButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.view === viewName);
  });
  Object.entries(els.views).forEach(([key, view]) => {
    view.classList.toggle("active", key === viewName);
  });
  renderOperatorProjectList();
  renderOperatorSteps();
  updateOperatorHeader();
}

function updateOperatorHeader() {
  if (!els.operatorHeaderProject) {
    return;
  }
  const showProject = state.activeView === "operator" && state.operatorWorkspaceOpen && state.selectedProject;
  document.body.classList.toggle("operator-workspace-active", Boolean(showProject));
  document.body.classList.toggle("operator-focus-mode", Boolean(showProject && state.operatorView.focusMode));
  els.operatorHeaderProject.hidden = !showProject;
  els.operatorHeaderProject.textContent = showProject ? `Operator | ${state.selectedProject.name}` : "";
}

function isAnyActionPanelOpen() {
  return els.actionPanels.some((panel) => !panel.hidden);
}

function updateAdminLayout() {
  const detailMode = Boolean(state.adminProjectOpen && state.selectedProject);
  if (els.adminProjectListPanel) {
    els.adminProjectListPanel.hidden = detailMode;
  }
  if (els.projectDetails) {
    els.projectDetails.hidden = !detailMode;
  }
  if (els.adminActionPanels) {
    els.adminActionPanels.hidden = !isAnyActionPanelOpen();
  }
  els.adminListActions.forEach((button) => {
    button.hidden = detailMode;
  });
  els.adminDetailActions.forEach((button) => {
    button.hidden = !detailMode;
  });
  if (els.adminPageTitle) {
    els.adminPageTitle.textContent = detailMode ? state.selectedProject.name : "Projekty";
  }
  if (els.adminPageSubtitle) {
    els.adminPageSubtitle.textContent = detailMode
      ? `Szczegóły projektu | ${statusLabel(state.selectedProject.status)} | PCB ${state.selectedProject.board_width || "-"} x ${state.selectedProject.board_height || "-"} mm`
      : "Lista projektów i przygotowanie produkcji.";
  }
}

function hideActionPanels() {
  els.actionPanels.forEach((panel) => {
    panel.hidden = true;
  });
  updateAdminLayout();
}

function showActionPanel(panelName) {
  const target = els.actionPanels.find((panel) => panel.dataset.actionPanel === panelName);
  if (!target) {
    return;
  }
  if (["editProject", "boardImage", "previewImages", "reimportProject", "supplementPoints", "addLine"].includes(panelName) && !state.selectedProject) {
    alert("Najpierw wybierz projekt.");
    return;
  }
  const shouldShow = target.hidden;
  hideActionPanels();
  target.hidden = !shouldShow;
  if (shouldShow && panelName === "addLine" && state.selectedProject) {
    els.stepForm.elements.projectId.value = state.selectedProject.id;
  }
  if (shouldShow && panelName === "editProject" && state.selectedProject) {
    fillEditProjectForm(state.selectedProject);
  }
  if (shouldShow && panelName === "pinIndexes") {
    renderPinIndexes();
  }
  updateAdminLayout();
}

function showAdminProjectList() {
  state.adminProjectOpen = false;
  hideActionPanels();
  renderProjectTable();
  renderProjectDetails();
  updateAdminLayout();
}

function fillEditProjectForm(project) {
  els.editProjectForm.elements.name.value = project.name || "";
  els.editProjectForm.elements.boardWidth.value = project.board_width ?? "";
  els.editProjectForm.elements.boardHeight.value = project.board_height ?? "";
  els.editProjectForm.elements.status.value = project.status === "active" ? "ready" : project.status || "draft";
}

function fillProjectSelects() {
  const stepSelect = els.stepForm.elements.projectId;
  const previousStep = stepSelect.value;
  stepSelect.innerHTML = state.projects
    .map((project) => `<option value="${project.id}">${escapeHtml(project.name)}</option>`)
    .join("");
  if (previousStep) {
    stepSelect.value = previousStep;
  }
}

function statusLabel(status) {
  const labels = {
    draft: "Szkic",
    imported: "Zaimportowany",
    needs_preparation: "Do przygotowania",
    prepared: "Przygotowany",
    ready: "Gotowy",
    active: "W produkcji",
    archived: "Archiwum",
  };
  return labels[status] || status || "-";
}

function isOperatorProject(project) {
  return project?.status === "ready";
}

function projectMatchesSearch(project, query) {
  if (!query) {
    return true;
  }
  const haystack = [
    project.name,
    project.status,
    project.step_count,
    project.point_count,
    project.created_at,
    project.updated_at,
  ].join(" ").toLowerCase();
  return haystack.includes(query.toLowerCase());
}

function renderProjectTable() {
  const query = els.projectSearch.value.trim();
  const projects = state.projects.filter((project) => projectMatchesSearch(project, query));

  if (!projects.length) {
    els.projectTableBody.innerHTML = `<tr><td colspan="8" class="muted">${state.projects.length ? "Brak wyników." : "Brak projektów."}</td></tr>`;
    return;
  }

  els.projectTableBody.innerHTML = projects
    .map((project) => {
      const active = state.selectedProject?.id === project.id ? " active" : "";
      const image = project.board_image_path ? '<span class="badge image-badge">Jest</span>' : '<span class="muted">Brak</span>';
      const openFeedback = Number(project.open_feedback_count || 0);
      return `
        <tr class="${active}" data-project-id="${project.id}">
          <td>
            <strong>${escapeHtml(project.name)}</strong>
            <span class="muted">${escapeHtml(project.board_width || "-")} x ${escapeHtml(project.board_height || "-")} mm</span>
          </td>
          <td><span class="badge">${escapeHtml(statusLabel(project.status))}</span>${openFeedback ? `<span class="badge feedback-badge">${openFeedback} zgł.</span>` : ""}</td>
          <td class="num">${project.step_count || 0}</td>
          <td class="num">${project.point_count || 0}</td>
          <td>${image}</td>
          <td>${escapeHtml(formatDate(project.created_at))}</td>
          <td>${escapeHtml(formatDate(project.updated_at))}</td>
          <td><button type="button" data-open-project="${project.id}">Otwórz</button></td>
        </tr>
      `;
    })
    .join("");

  els.projectTableBody.querySelectorAll("[data-open-project]").forEach((button) => {
    const project = projects.find((item) => item.id === button.dataset.openProject);
    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "danger";
    deleteButton.dataset.deleteProject = button.dataset.openProject;
    deleteButton.dataset.projectName = project?.name || "";
    deleteButton.textContent = "Usuń";
    button.insertAdjacentElement("afterend", deleteButton);
  });

  els.projectTableBody.querySelectorAll("[data-project-id]").forEach((row) => {
    row.addEventListener("click", (event) => {
      if (event.target.closest("button")) {
        return;
      }
      selectProject(row.dataset.projectId);
    });
  });
  els.projectTableBody.querySelectorAll("[data-open-project]").forEach((button) => {
    button.addEventListener("click", () => selectProject(button.dataset.openProject));
  });
  els.projectTableBody.querySelectorAll("[data-delete-project]").forEach((button) => {
    button.addEventListener("click", () => deleteProject(button.dataset.deleteProject, button.dataset.projectName));
  });
}

async function loadProjects() {
  const payload = await api("/api/projects");
  state.projects = payload.projects;
  fillProjectSelects();

  if (state.selectedProject && state.projects.some((project) => project.id === state.selectedProject.id)) {
    state.selectedProject = await loadProject(state.selectedProject.id);
  } else if (state.selectedProject) {
    state.selectedProject = null;
    state.adminProjectOpen = false;
    hideActionPanels();
  }

  renderProjectTable();
  renderProjectDetails();
  updateAdminLayout();
  renderOperatorProjectList();
  renderOperatorSteps();
}

async function loadPinIndexes() {
  const payload = await api("/api/pin-indexes");
  state.pinIndexes = payload.pinIndexes || [];
  renderPinIndexes();
}

async function refreshData() {
  await loadPinIndexes();
  await loadProjects();
}

async function selectProject(projectId, tabName) {
  if (tabName) {
    state.activeProjectTab = tabName;
  }
  state.selectedProject = await loadProject(projectId);
  state.adminProjectOpen = true;
  hideActionPanels();
  renderProjectTable();
  renderProjectDetails();
  updateAdminLayout();
  renderOperatorSteps();
  updateOperatorHeader();
}

function operatorProjects() {
  return state.projects.filter(isOperatorProject);
}

function renderOperatorProjectList() {
  if (!els.operatorProjectList) {
    return;
  }
  const query = (els.operatorProjectSearch?.value || "").trim();
  const projects = operatorProjects().filter((project) => projectMatchesSearch(project, query));
  els.operatorProjectBrowser.hidden = state.operatorWorkspaceOpen;
  if (!projects.length) {
    els.operatorProjectList.innerHTML = `
      <div class="empty-state">
        <strong>${operatorProjects().length ? "Brak wyników" : "Brak projektów dla operatora"}</strong>
        <span>Admin musi przekazać projekt ze statusem Gotowy albo W produkcji.</span>
      </div>
    `;
    return;
  }
  els.operatorProjectList.innerHTML = projects.map((project) => {
    const image = project.board_image_path
      ? `<img src="${escapeHtml(boardImageUrl(project.board_image_path, project.updated_at))}" alt="PCB ${escapeHtml(project.name)}">`
      : '<div class="operator-project-thumb-placeholder">PCB</div>';
    const feedbackCount = Number(project.open_feedback_count || 0);
    return `
      <button type="button" class="operator-project-card" data-open-operator-project="${project.id}">
        <span class="operator-project-thumb">${image}</span>
        <span class="operator-project-main">
          <strong>${escapeHtml(project.name)}</strong>
          <em>${escapeHtml(statusLabel(project.status))}</em>
        </span>
        <span class="operator-project-meta">
          <span>${project.step_count || project.steps?.length || 0} kroków</span>
          <span>${project.point_count || project.points?.length || 0} punktów</span>
          ${feedbackCount ? `<span class="feedback-pill">${feedbackCount} zgłoszeń</span>` : ""}
        </span>
      </button>
    `;
  }).join("");
  els.operatorProjectList.querySelectorAll("[data-open-operator-project]").forEach((button) => {
    button.addEventListener("click", () => openOperatorProject(button.dataset.openOperatorProject));
  });
}

async function openOperatorProject(projectId) {
  state.selectedProject = await loadProject(projectId);
  state.operatorWorkspaceOpen = true;
  state.operatorActiveStepId = null;
  state.operatorPreviewImage = null;
  setView("operator");
}

function closeOperatorProject() {
  state.operatorWorkspaceOpen = false;
  state.operatorActiveStepId = null;
  state.operatorPreviewImage = null;
  renderOperatorProjectList();
  renderOperatorSteps();
  updateOperatorHeader();
}

async function deleteProject(projectId, projectName) {
  const confirmed = window.confirm(`Usunąć projekt "${projectName}"?\n\nTa operacja usunie też linie, punkty, importy i sesje tego projektu.`);
  if (!confirmed) {
    return;
  }
  await api(`/api/projects/${projectId}`, {
    method: "DELETE",
  });
  if (state.selectedProject?.id === projectId) {
    state.selectedProject = null;
    state.adminProjectOpen = false;
    hideActionPanels();
  }
  await loadProjects();
}

function filenameFromContentDisposition(header, fallback) {
  const value = String(header || "");
  const utfMatch = value.match(/filename\*=UTF-8''([^;]+)/i);
  if (utfMatch) {
    try {
      return decodeURIComponent(utfMatch[1]).trim() || fallback;
    } catch (error) {
      return utfMatch[1].trim() || fallback;
    }
  }
  const asciiMatch = value.match(/filename="([^"]+)"/i) || value.match(/filename=([^;]+)/i);
  return asciiMatch ? asciiMatch[1].trim() : fallback;
}

function fallbackDownloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function downloadProjectHtml(projectId) {
  const response = await fetch(`/api/projects/${projectId}/operator-html`);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Nie udało się wygenerować HTML.");
  }

  const project = state.projects.find((item) => item.id === projectId) || state.selectedProject;
  const fallbackName = `${project?.name || "projekt"}.html`;
  const filename = filenameFromContentDisposition(response.headers.get("Content-Disposition"), fallbackName);
  const blob = await response.blob();

  if (window.showDirectoryPicker) {
    try {
      const directoryHandle = await window.showDirectoryPicker({
        id: "msx-tht-inserter-html",
        mode: "readwrite",
      });
      const fileHandle = await directoryHandle.getFileHandle(filename, { create: true });
      const writable = await fileHandle.createWritable();
      await writable.write(blob);
      await writable.close();
      alert(`Zapisano HTML:\n${filename}`);
      return;
    } catch (error) {
      if (error?.name === "AbortError") {
        return;
      }
      console.warn("Nie udało się zapisać HTML do wybranego folderu.", error);
    }
  }

  fallbackDownloadBlob(blob, filename);
}

function renderPinIndexes() {
  if (!els.pinIndexList) {
    return;
  }
  if (!state.pinIndexes.length) {
    els.pinIndexList.innerHTML = '<div class="muted">Brak aktywnych indeksów pinowych.</div>';
    return;
  }

  els.pinIndexList.innerHTML = state.pinIndexes.map((item) => `
    <div class="pin-index-row">
      <div>
        <strong>${escapeHtml(item.medcom_index)}</strong>
        ${item.note ? `<span>${escapeHtml(item.note)}</span>` : '<span>Indeks traktowany jako pin do przygotowania</span>'}
      </div>
      <button type="button" data-remove-pin-index="${escapeHtml(item.medcom_index)}" title="Usuń indeks">X</button>
    </div>
  `).join("");

  els.pinIndexList.querySelectorAll("[data-remove-pin-index]").forEach((button) => {
    button.addEventListener("click", () => removePinIndex(button.dataset.removePinIndex));
  });
}

async function removePinIndex(medcomIndex) {
  const confirmed = window.confirm(`Usunąć indeks "${medcomIndex}" z listy pinowej?\n\nPo usunięciu nie będzie trafiał do zakładki Przygotowanie.`);
  if (!confirmed) {
    return;
  }
  const payload = await api(`/api/pin-indexes/${encodeURIComponent(medcomIndex)}`, {
    method: "DELETE",
  });
  state.pinIndexes = payload.pinIndexes || [];
  renderPinIndexes();
  renderProjectDetails();
}

async function loadProject(projectId) {
  const payload = await api(`/api/projects/${projectId}`);
  return payload.project;
}

function latestEventForStep(stepId) {
  return (state.selectedProject?.operator_step_statuses || [])
    .find((item) => Number(item.step_id) === Number(stepId)) || null;
}

function boardImageUrl(path, version = "") {
  if (!path) {
    return "";
  }
  const normalized = String(path).replaceAll("\\", "/");
  const url = `/uploads/${normalized.replace(/^.*data\/uploads\//, "")}`;
  return version ? `${url}?v=${encodeURIComponent(version)}` : url;
}

function projectPreviewDefinitions(project) {
  return [
    {
      key: "tht",
      label: "Podgl\u0105d THT",
      path: project?.tht_preview_image_path || "",
    },
    {
      key: "labeling",
      label: "Podgl\u0105d Oklejanie",
      path: project?.labeling_preview_image_path || "",
    },
  ];
}

function projectPreviewImages(project) {
  return projectPreviewDefinitions(project).filter((item) => item.path);
}

function projectPreviewImage(project, key) {
  return projectPreviewImages(project).find((item) => item.key === key) || null;
}

function projectContours(project) {
  return Array.isArray(project?.board_contours?.contours) ? project.board_contours.contours : [];
}

function projectContourSummary(project) {
  return project?.board_contours?.summary || {};
}

function contourDesignators(contour) {
  return Array.isArray(contour?.designators)
    ? contour.designators.map((item) => String(item || "").toUpperCase()).filter(Boolean)
    : [];
}

function contourMatchesDesignators(contour, designators) {
  if (!designators?.size) {
    return true;
  }
  return contourDesignators(contour).some((designator) => designators.has(designator));
}

function contoursForStep(project, step) {
  const designators = new Set(stepDesignatorsForPoints(step));
  return projectContours(project).filter((contour) => contourMatchesDesignators(contour, designators));
}

function renderImportSummary(summary, project) {
  const warnings = [];
  if (summary.missingInPp?.length) {
    warnings.push(`brak w P&P: ${summary.missingInPp.slice(0, 12).join(", ")}${summary.missingInPp.length > 12 ? "..." : ""}`);
  }
  if (summary.extraInPp?.length) {
    warnings.push(`nadmiar w P&P: ${summary.extraInPp.slice(0, 12).join(", ")}${summary.extraInPp.length > 12 ? "..." : ""}`);
  }
  if (summary.bomDuplicateDesignators?.length) {
    warnings.push(`duplikaty BOM: ${summary.bomDuplicateDesignators.join(", ")}`);
  }

  els.importSummary.innerHTML = `
    <strong>${escapeHtml(project.name)}</strong>: utworzono ${summary.createdSteps} kroków i ${summary.createdPoints} punktów.
    Dopasowano ${summary.matchedDesignators} z ${summary.bomDesignators} desygnatorów BOM.
    ${project.board_image_path ? "Zdjęcie PCB zapisane." : ""}
    ${warnings.length ? `<br>${escapeHtml(warnings.join(" | "))}` : ""}
  `;
}

function shortList(items, limit = 14) {
  const values = Array.isArray(items) ? items.filter(Boolean) : [];
  if (!values.length) {
    return "-";
  }
  const suffix = values.length > limit ? ` ... +${values.length - limit}` : "";
  return `${values.slice(0, limit).join(", ")}${suffix}`;
}

function renderPointSupplementSummary(summary) {
  if (!els.supplementPointsSummary) {
    return;
  }
  const added = summary?.addedDesignators || [];
  const stillMissing = summary?.stillMissingInPp || [];
  const ignored = summary?.ignoredPpDesignators || [];
  const duplicates = summary?.ppDuplicateDesignators || [];
  els.supplementPointsSummary.innerHTML = `
    Dodano <strong>${summary?.addedPoints || 0}</strong> punkt\u00f3w z P&amp;P.
    ${added.length ? `<br>Dopi\u0119te: ${escapeHtml(shortList(added))}` : ""}
    ${stillMissing.length ? `<br>Nadal bez punktu w P&amp;P: ${escapeHtml(shortList(stillMissing))}` : ""}
    ${duplicates.length ? `<br>Duplikaty w P&amp;P pomini\u0119te: ${escapeHtml(shortList(duplicates))}` : ""}
    ${ignored.length ? `<br>Zignorowano spoza linii monta\u017cowych: ${ignored.length}` : ""}
  `;
}

function renderProjectDetails() {
  const project = state.selectedProject;
  if (!project) {
    els.projectDetails.innerHTML = `
      <div class="empty-state">
        <strong>Wybierz projekt</strong>
        <span>Po wyborze zobaczysz import, linie montażowe, punkty P&amp;P, obraz PCB i ustawienia operatora.</span>
      </div>
    `;
    return;
  }

  els.projectDetails.innerHTML = `
    <div class="details-head">
      <div>
        <h2>${escapeHtml(project.name)}</h2>
        <p>Status: ${escapeHtml(statusLabel(project.status))} | PCB: ${escapeHtml(project.board_width || "-")} x ${escapeHtml(project.board_height || "-")} mm</p>
      </div>
      <div class="details-actions">
        <button type="button" data-panel="editProject">Edytuj</button>
        <button type="button" data-panel="boardImage">${project.board_image_path ? "Podmień PCB" : "Dodaj PCB"}</button>
        <button type="button" data-panel="reimportProject">Reimport</button>
        <button type="button" data-panel="supplementPoints">Uzupe\u0142nij P&amp;P</button>
        <button type="button" class="primary" data-export-project-html="${project.id}" ${project.board_image_path ? "" : "disabled"}>Generuj HTML</button>
      </div>
      ${renderBoardThumb(project)}
    </div>
    <div class="tabs">
      ${renderTabButton("summary", "Podsumowanie")}
      ${renderTabButton("preparation", "Przygotowanie")}
      ${renderTabButton("lines", "Linie montażowe")}
      ${renderTabButton("preview", "Podgl\u0105d")}
      ${renderTabButton("points", "P&P / punkty")}
      ${renderTabButton("contours", "Kontury")}
      ${renderTabButton("image", "Obraz PCB")}
      ${renderTabButton("operatorPreviews", "Podgl\u0105dy operatora")}
      ${renderTabButton("calibration", "Kalibracja")}
      ${renderTabButton("polarity", "Polaryzacja")}
      ${renderTabButton("operator", "Uwagi operatora")}
    </div>
    <div class="tab-content">
      ${renderActiveProjectTab(project)}
    </div>
  `;

  els.projectDetails.querySelectorAll("[data-project-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeProjectTab = button.dataset.projectTab;
      renderProjectDetails();
    });
  });
  els.projectDetails.querySelectorAll("[data-panel]").forEach((button) => {
    button.addEventListener("click", () => showActionPanel(button.dataset.panel));
  });
  els.projectDetails.querySelectorAll("[data-consolidate-pins]").forEach((button) => {
    button.addEventListener("click", consolidatePinSteps);
  });
  els.projectDetails.querySelectorAll("[data-release-project]").forEach((button) => {
    button.addEventListener("click", releaseProjectToOperator);
  });
  els.projectDetails.querySelectorAll("[data-set-project-status]").forEach((button) => {
    button.addEventListener("click", () => setProjectStatus(button.dataset.setProjectStatus));
  });
  els.projectDetails.querySelectorAll("[data-export-project-html]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      const previousText = button.textContent;
      button.textContent = "Generuję...";
      try {
        await downloadProjectHtml(button.dataset.exportProjectHtml);
      } catch (error) {
        alert(error.message);
      } finally {
        button.disabled = false;
        button.textContent = previousText;
      }
    });
  });
  els.projectDetails.querySelectorAll("[data-step-notes-form]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      saveStepNotes(form);
    });
  });
  els.projectDetails.querySelectorAll("[data-skip-step]").forEach((button) => {
    button.addEventListener("click", () => skipStep(button.dataset.skipStep));
  });
  els.projectDetails.querySelectorAll("[data-delete-step]").forEach((button) => {
    button.addEventListener("click", () => deleteStep(button.dataset.deleteStep));
  });
  els.projectDetails.querySelectorAll("[data-open-admin-preview-step]").forEach((button) => {
    button.addEventListener("click", () => {
      state.adminPreviewStepId = Number(button.dataset.openAdminPreviewStep);
      state.activeProjectTab = "preview";
      renderProjectDetails();
    });
  });
  attachLineProTools();
  attachImageTools();
  attachOperatorPreviewAdminTools();
  attachGerberContourTools();
  attachCalibrationTools();
  attachPolarityTools();
  attachAdminPreviewTools();
  els.projectDetails.querySelectorAll("[data-feedback-form]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      updateFeedbackStatus(form);
    });
  });
  els.projectDetails.querySelectorAll("[data-open-feedback-step]").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeProjectTab = "lines";
      state.proEditorStepId = Number(button.dataset.openFeedbackStep);
      renderProjectDetails();
    });
  });
  els.projectDetails.querySelectorAll("[data-preparation-split-form]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      splitPreparationLine(form);
    });
    form.addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (!button) {
        return;
      }
      if (button.dataset.addSegment !== undefined) {
        addPreparationSegment(form);
      }
      if (button.dataset.mergeSegments !== undefined) {
        mergePreparationSegments(form);
      }
      if (button.dataset.splitSegments !== undefined) {
        splitSelectedPreparationSegments(form);
      }
      if (button.dataset.noPreparation !== undefined) {
        markPreparationNotNeeded(form);
      }
      if (button.dataset.removeSegment !== undefined) {
        removePreparationSegment(button);
      }
    });
    form.addEventListener("input", () => updatePreparationPreview(form));
    updatePreparationPreview(form);
  });
}

function renderTabButton(tabName, label) {
  const active = state.activeProjectTab === tabName ? " active" : "";
  return `<button type="button" class="tab-button${active}" data-project-tab="${tabName}">${label}</button>`;
}

function renderActiveProjectTab(project) {
  if (state.activeProjectTab === "preparation") {
    return renderPreparationTab(project);
  }
  if (state.activeProjectTab === "lines") {
    return renderLinesTabPro(project);
  }
  if (state.activeProjectTab === "preview") {
    return renderAdminPreviewTab(project);
  }
  if (state.activeProjectTab === "points") {
    return renderPointsTab(project);
  }
  if (state.activeProjectTab === "contours") {
    return renderContoursTab(project);
  }
  if (state.activeProjectTab === "image") {
    return renderImageTab(project);
  }
  if (state.activeProjectTab === "operatorPreviews") {
    return renderOperatorPreviewsTab(project);
  }
  if (state.activeProjectTab === "calibration") {
    return renderCalibrationTab(project);
  }
  if (state.activeProjectTab === "polarity") {
    return renderPolarityTab(project);
  }
  if (state.activeProjectTab === "operator") {
    return renderOperatorFeedbackTab(project);
  }
  return renderSummaryTab(project);
}

function renderBoardThumb(project) {
  if (project.board_image_path) {
    return `<img class="board-preview" src="${escapeHtml(boardImageUrl(project.board_image_path, project.updated_at))}" alt="Obraz PCB">`;
  }
  return '<div class="board-placeholder">PCB</div>';
}

function stepHasMissingPoint(step) {
  return String(step.notes || "").includes("Brak punktu P&P");
}

function stepIsSkipped(step) {
  return String(step.notes || "").includes("Pominięte w montażu");
}

function unresolvedMissingPointSteps(project) {
  return (project.steps || []).filter((step) => stepHasMissingPoint(step) && !stepIsSkipped(step));
}

function projectReadiness(project) {
  const latestImport = project.imports?.[0]?.summary || null;
  const steps = project.steps || [];
  const points = project.points || [];
  const extraInPp = latestImport?.extraInPp || [];
  const bomDuplicateDesignators = latestImport?.bomDuplicateDesignators || [];
  const bomConflictingDesignators = latestImport?.bomConflictingDesignators || [];
  const ppDuplicateDesignators = latestImport?.ppDuplicateDesignators || [];
  const preparationCandidates = steps.filter(isPreparationCandidate);
  const duplicateCount = bomDuplicateDesignators.length + bomConflictingDesignators.length + ppDuplicateDesignators.length;
  const missingPointDesignatorList = missingPointDesignators(project);
  const checks = [
    {
      label: "BOM i P&P zaimportowane",
      ok: Boolean(latestImport) && steps.length > 0,
      detail: `${steps.length} linii, ${points.length} punktów`,
    },
    {
      label: "Obraz PCB dołączony",
      ok: Boolean(project.board_image_path),
      detail: project.board_image_path ? "jest obraz płytki" : "dodaj obraz płytki w projekcie",
    },
    {
      label: "Punkty P&P obecne",
      ok: points.length > 0,
      detail: points.length ? `${points.length} punktów pozycyjnych` : "brak punktów z P&P",
    },
    {
      label: "Wyjątki bez punktu P&P rozliczone",
      ok: Boolean(latestImport) && missingPointDesignatorList.length === 0,
      detail: !latestImport
        ? "brak danych importu"
        : missingPointDesignatorList.length
          ? `bez punktu: ${readinessShortList(missingPointDesignatorList)}`
          : "wszystkie aktywne linie maj\u0105 punkty P&P",
    },
    {
      label: "BOM/P&P bez duplikatów",
      ok: Boolean(latestImport) && duplicateCount === 0,
      detail: latestImport
        ? readinessDuplicateDetail(bomDuplicateDesignators, bomConflictingDesignators, ppDuplicateDesignators)
        : "brak danych importu",
    },
    {
      label: "P&P poza BOM THT",
      ok: true,
      detail: latestImport
        ? `${extraInPp.length} punktów SMD/innych pozycji ignorowanych w montażu THT`
        : "brak danych importu",
      info: true,
    },
    {
      label: "Indeksy pinowe skonfigurowane",
      ok: state.pinIndexes.length > 0,
      detail: `${state.pinIndexes.length} aktywnych indeksów`,
    },
    {
      label: "Przygotowanie pinów zakończone",
      ok: preparationCandidates.length === 0,
      detail: preparationCandidates.length
        ? `zostało ${preparationCandidates.length} linii do decyzji`
        : "brak otwartych pozycji pinowych",
    },
  ];
  const blockers = checks.filter((check) => !check.ok);
  return {
    checks,
    blockers,
    ready: blockers.length === 0,
  };
}

function readinessShortList(items, limit = 5) {
  const cleanItems = (items || []).filter(Boolean);
  if (!cleanItems.length) {
    return "brak";
  }
  const shown = cleanItems.slice(0, limit).join(", ");
  const rest = cleanItems.length > limit ? ` +${cleanItems.length - limit}` : "";
  return `${shown}${rest}`;
}

function readinessDuplicateDetail(bomDuplicates, bomConflicts, ppDuplicates) {
  const parts = [];
  if (bomDuplicates.length) {
    parts.push(`duplikaty BOM: ${readinessShortList(bomDuplicates)}`);
  }
  if (bomConflicts.length) {
    parts.push(`konflikty BOM: ${readinessShortList(bomConflicts)}`);
  }
  if (ppDuplicates.length) {
    parts.push(`duplikaty P&P: ${readinessShortList(ppDuplicates)}`);
  }
  return parts.length ? parts.join(" | ") : "brak duplikatów/konfliktów";
}

function renderReadinessPanel(project) {
  const readiness = projectReadiness(project);
  const published = isOperatorProject(project);
  const canPublish = readiness.ready && !published;
  const visibilityText = published
    ? "Operator widzi ten projekt na swojej liscie."
    : "Operator nie widzi tego projektu.";
  const title = published
    ? "Projekt przekazany do operatora"
    : readiness.ready
      ? "Projekt gotowy do przekazania"
      : "Projekt nie jest jeszcze gotowy";
  const actionLabel = published
    ? statusLabel(project.status)
    : readiness.ready
      ? "Przekaż do operatora"
      : "Uzupełnij braki";
  return `
    <section class="readiness-panel ${readiness.ready ? "ready" : "blocked"}">
      <div class="readiness-head">
        <div>
          <strong>${escapeHtml(title)}</strong>
          <span>Status: ${escapeHtml(statusLabel(project.status))} | ${escapeHtml(visibilityText)}</span>
          <span>${readiness.ready ? "Wszystkie warunki produkcyjne są spełnione." : `Blokady: ${readiness.blockers.length}`}</span>
        </div>
        <div class="project-status-actions">
          <button type="button" class="primary" data-set-project-status="ready" ${canPublish ? "" : "disabled"}>Oznacz OK dla operatora</button>
          <button type="button" data-set-project-status="prepared" ${published ? "" : "disabled"}>Cofnij z operatora</button>
          <button type="button" data-panel="editProject">Inny status</button>
        </div>
      </div>
      <div class="readiness-list">
        ${readiness.checks.map((check) => `
          <div class="readiness-item ${check.info ? "info" : check.ok ? "ok" : "missing"}">
            <span>${check.info ? "i" : check.ok ? "OK" : "!"}</span>
            <div>
              <strong>${escapeHtml(check.label)}</strong>
              <em>${escapeHtml(check.detail)}</em>
            </div>
          </div>
        `).join("")}
      </div>
    </section>
  `;
}

function renderProjectChangeHistory(project) {
  const changes = (project.changes || []).slice(0, 6);
  if (!changes.length) {
    return "";
  }
  return `
    <div class="summary-box project-change-history">
      <strong>Historia zmian technologii</strong>
      ${changes.map((change) => `
        <span>
          ${escapeHtml(formatDate(change.created_at))} | ${escapeHtml(change.description || change.change_type)}
        </span>
      `).join("")}
    </div>
  `;
}

function renderSummaryTab(project) {
  const latestImport = project.imports?.[0]?.summary;
  const missing = missingPointDesignators(project).length;
  const extra = latestImport?.extraInPp?.length || 0;
  return `
    <div class="stat-grid">
      <div><strong>${project.steps?.length || 0}</strong><span>linie montażowe</span></div>
      <div><strong>${project.points?.length || 0}</strong><span>punkty PCB</span></div>
      <div><strong>${latestImport ? `${latestImport.matchedDesignators}/${latestImport.bomDesignators}` : "-"}</strong><span>BOM / P&amp;P</span></div>
      <div><strong>${missing}</strong><span>wyjątki bez punktu</span></div>
    </div>
    ${renderReadinessPanel(project)}
    <div class="summary-grid">
      <div class="summary-box">
        <strong>Dane projektu</strong>
        <span>Utworzono: ${escapeHtml(formatDate(project.created_at))}</span>
        <span>Modyfikowano: ${escapeHtml(formatDate(project.updated_at))}</span>
        <span>Podgl\u0105d THT: ${project.tht_preview_image_path ? "do\u0142\u0105czony" : "brak"}</span>
        <span>Podgl\u0105d Oklejanie: ${project.labeling_preview_image_path ? "do\u0142\u0105czony" : "brak"}</span>
        <span>Obraz PCB: ${project.board_image_path ? "dołączony" : "brak"}</span>
      </div>
      <div class="summary-box">
        <strong>Walidacja importu</strong>
        <span>Nadmiarowe punkty P&amp;P: ${extra}</span>
        <span>Duplikaty BOM: ${latestImport?.bomDuplicateDesignators?.length || 0}</span>
        <span>Duplikaty P&amp;P: ${latestImport?.ppDuplicateDesignators?.length || 0}</span>
      </div>
    </div>
    ${renderProjectChangeHistory(project)}
    <div class="project-actions">
      <button type="button" data-panel="editProject">Edytuj projekt</button>
      <button type="button" data-panel="boardImage">${project.board_image_path ? "Podmień obraz PCB" : "Dodaj obraz PCB"}</button>
      <button type="button" data-panel="reimportProject">Reimport Exceli</button>
      <button type="button" data-panel="supplementPoints">Uzupe\u0142nij punkty P&amp;P</button>
      <button type="button" class="primary" data-export-project-html="${project.id}" ${project.board_image_path ? "" : "disabled"}>Generuj HTML</button>
    </div>
  `;
}

function splitDesignators(value) {
  return String(value || "")
    .split(/[,\s;]+/)
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean);
}

function sortDesignators(items) {
  return items.slice().sort((a, b) => String(a).localeCompare(String(b), "pl", {
    numeric: true,
    sensitivity: "base",
  }));
}

function missingPointDesignators(project) {
  const pointDesignators = new Set((project.points || []).map((point) => String(point.designator || "").toUpperCase()));
  const missing = new Set();
  (project.steps || []).filter((step) => !stepIsSkipped(step)).forEach((step) => {
    stepDesignatorsForPoints(step).forEach((designator) => {
      const cleanDesignator = String(designator || "").toUpperCase();
      if (cleanDesignator && !pointDesignators.has(cleanDesignator)) {
        missing.add(cleanDesignator);
      }
    });
  });
  return sortDesignators(Array.from(missing));
}

function extractPinCount(value, fallback = 1) {
  const match = String(value || "").match(/\b(\d+)\s*PIN\b/i);
  if (!match) {
    return fallback;
  }
  const pinCount = Number.parseInt(match[1], 10);
  return Number.isFinite(pinCount) && pinCount > 0 ? pinCount : fallback;
}

function pinCountsFromValue(value) {
  return Array.from(String(value || "").matchAll(/\b(\d+)\s*PIN\b/ig))
    .map((match) => Number.parseInt(match[1], 10))
    .filter((pinCount) => Number.isFinite(pinCount) && pinCount > 0);
}

function isPreparationCandidate(step) {
  const value = String(step.value || "");
  const notes = String(step.notes || "");
  if (
    stepSegments(step).length
    || /^\d+\s*PIN\s*(\(|$)/i.test(value)
    || notes.includes("Rozbite w przygotowaniu")
    || notes.includes("Bez przygotowania")
  ) {
    return false;
  }
  const designators = splitDesignators(step.designators);
  const medcomIndex = normalizeMedcomIndex(step.medcom_index);
  return pinIndexSet().has(medcomIndex) && designators.length > 1;
}

function preparationReason(step) {
  if (pinIndexSet().has(normalizeMedcomIndex(step.medcom_index))) {
    return "indeks pinowy do przygotowania";
  }
  return "pozycja wymaga decyzji technologicznej";
}

function renderPreparationTab(project) {
  const candidates = (project.steps || []).filter(isPreparationCandidate);
  const prepared = (project.steps || []).filter((step) => stepSegments(step).length);
  if (!candidates.length && !prepared.length) {
    return `
      <div class="empty-state">
        <strong>Brak pozycji do przygotowania</strong>
        <span>System nie znalazł linii pinowych wymagających rozbicia.</span>
      </div>
    `;
  }

  return `
    <div class="prep-list">
      ${candidates.length ? `
        <div class="prep-section-title">
          <strong>Do przygotowania</strong>
          <span>Linie źródłowe z BOM, które można rozbić na fizyczne odcinki.</span>
        </div>
        ${candidates.map((step) => renderPreparationCard(step, false)).join("")}
      ` : ""}
      ${prepared.length ? `
        <div class="prep-section-title">
          <strong>Już przygotowane / popraw</strong>
          <span>Te linie zostały już rozbite, ale możesz zmienić odcinki i zapisać korektę.</span>
        </div>
        ${prepared.map((step) => renderPreparationCard(step, true)).join("")}
      ` : ""}
    </div>
  `;
}

function renderPreparationCard(step, prepared = false) {
  const designators = splitDesignators(step.designators);
  const defaultPinCount = extractPinCount(step.value, 1);
  const segments = prepared && stepSegments(step).length
    ? stepSegments(step)
    : designators.map((designator) => ({ designators: [designator], pinCount: defaultPinCount }));
  return `
    <article class="prep-card${prepared ? " prepared" : ""}">
      <div class="prep-head">
        <div>
          <strong>${step.step_no}. ${escapeHtml(renderStepValue(step))}</strong>
          <span>${escapeHtml(step.medcom_index || "-")} | ${prepared ? "gotowe, można poprawić" : escapeHtml(preparationReason(step))}</span>
        </div>
        <span class="badge">${prepared ? `${segments.length} odc.` : `${designators.length} des.`}</span>
      </div>
      <form data-preparation-split-form data-step-id="${step.id}" data-original-designators="${escapeHtml(designators.join(","))}" data-default-pin-count="${defaultPinCount}">
        <div class="prep-toolbar">
          <button type="button" data-merge-segments>Połącz</button>
          <button type="button" data-split-segments>Rozdziel</button>
          <button type="button" data-add-segment>Dodaj</button>
          ${prepared ? "" : '<button type="button" data-no-preparation>Nie wymaga przygotowania</button>'}
        </div>
        <div class="prep-segments" data-prep-segments>
          ${segments.map((segment) => renderPreparationSegmentRow(
            Array.isArray(segment.designators) ? segment.designators.join(",") : "",
            Number(segment.pinCount) || defaultPinCount,
          )).join("")}
        </div>
        <div class="prep-preview" data-prep-preview></div>
        <label>
          Uwaga technologiczna
          <input name="technologyNote" placeholder="np. ciąć z listwy 1x40 H12">
        </label>
        <button type="submit" class="primary">${prepared ? "Zapisz poprawki" : "Rozbij na linie operatorskie"}</button>
      </form>
    </article>
  `;
}

function renderPreparationSegmentRow(designators = "", pinCount = 1) {
  return `
    <div class="prep-segment-row" data-prep-segment-row>
      <input class="prep-check" type="checkbox" data-segment-select title="Zaznacz">
      <label class="prep-segment-name">
        <span>Odcinek</span>
        <input data-segment-designators value="${escapeHtml(designators)}" placeholder="TP8,TP9,TP10">
      </label>
      <label class="prep-segment-pins">
        <span>PIN</span>
        <input data-segment-pin-count type="number" min="1" max="80" value="${escapeHtml(pinCount)}" inputmode="numeric">
      </label>
      <button type="button" data-remove-segment title="Usuń">X</button>
    </div>
  `;
}

function readPreparationSegments(form) {
  return Array.from(form.querySelectorAll("[data-prep-segment-row]"))
    .map((row) => {
      const designators = splitDesignators(row.querySelector("[data-segment-designators]")?.value || "");
      const pinCount = Number.parseInt(row.querySelector("[data-segment-pin-count]")?.value || "0", 10);
      return { pinCount, designators, quantity: 1 };
    })
    .filter((segment) => Number.isFinite(segment.pinCount) && segment.pinCount > 0 && segment.designators.length);
}

function validatePreparationSegments(form, segments) {
  const original = splitDesignators(form.dataset.originalDesignators || "");
  const originalSet = new Set(original);
  const seen = new Set();
  const duplicates = new Set();
  const unknown = new Set();

  segments.forEach((segment) => {
    segment.designators.forEach((designator) => {
      if (seen.has(designator)) {
        duplicates.add(designator);
      }
      if (!originalSet.has(designator)) {
        unknown.add(designator);
      }
      seen.add(designator);
    });
  });

  const missing = original.filter((designator) => !seen.has(designator));
  const errors = [];
  if (duplicates.size) {
    errors.push(`Powtórzone desygnatory: ${Array.from(duplicates).join(", ")}`);
  }
  if (unknown.size) {
    errors.push(`Desygnatory spoza linii: ${Array.from(unknown).join(", ")}`);
  }
  if (missing.length) {
    errors.push(`Nieprzypisane desygnatory: ${missing.join(", ")}`);
  }
  return errors;
}

function addPreparationSegment(form) {
  const defaultPinCount = Number.parseInt(form.dataset.defaultPinCount || "1", 10) || 1;
  form.querySelector("[data-prep-segments]").insertAdjacentHTML("beforeend", renderPreparationSegmentRow("", defaultPinCount));
  updatePreparationPreview(form);
}

function mergePreparationSegments(form) {
  const rows = Array.from(form.querySelectorAll("[data-prep-segment-row]"));
  const selectedRows = rows.filter((row) => row.querySelector("[data-segment-select]")?.checked);
  if (selectedRows.length < 2) {
    alert("Zaznacz minimum dwa odcinki do połączenia.");
    return;
  }

  const designators = selectedRows.flatMap((row) => splitDesignators(row.querySelector("[data-segment-designators]")?.value || ""));
  const pinCount = selectedRows.reduce((total, row) => {
    const value = Number.parseInt(row.querySelector("[data-segment-pin-count]")?.value || "0", 10);
    return total + (Number.isFinite(value) && value > 0 ? value : 0);
  }, 0);
  const uniqueDesignators = Array.from(new Set(designators));
  const targetRow = selectedRows[0];
  targetRow.querySelector("[data-segment-designators]").value = uniqueDesignators.join(",");
  targetRow.querySelector("[data-segment-pin-count]").value = pinCount || uniqueDesignators.length || 1;
  targetRow.querySelector("[data-segment-select]").checked = false;
  selectedRows.slice(1).forEach((row) => row.remove());
  updatePreparationPreview(form);
}

function splitSelectedPreparationSegments(form) {
  const rows = Array.from(form.querySelectorAll("[data-prep-segment-row]"));
  const selectedRows = rows.filter((row) => row.querySelector("[data-segment-select]")?.checked);
  if (!selectedRows.length) {
    alert("Zaznacz odcinek do rozdzielenia.");
    return;
  }

  let changed = false;
  selectedRows.forEach((row) => {
    const designators = splitDesignators(row.querySelector("[data-segment-designators]")?.value || "");
    if (designators.length < 2) {
      row.querySelector("[data-segment-select]").checked = false;
      return;
    }
    const pinCount = Number.parseInt(row.querySelector("[data-segment-pin-count]")?.value || "1", 10) || 1;
    row.insertAdjacentHTML(
      "afterend",
      designators.map((designator) => renderPreparationSegmentRow(designator, Math.max(1, Math.floor(pinCount / designators.length)))).join(""),
    );
    row.remove();
    changed = true;
  });

  if (!changed) {
    alert("Zaznaczone odcinki są już pojedyncze.");
  }
  updatePreparationPreview(form);
}

function removePreparationSegment(button) {
  const form = button.closest("form");
  const row = button.closest("[data-prep-segment-row]");
  if (!form || !row) {
    return;
  }
  row.remove();
  if (!form.querySelector("[data-prep-segment-row]")) {
    addPreparationSegment(form);
    return;
  }
  updatePreparationPreview(form);
}

function updatePreparationPreview(form) {
  const preview = form.querySelector("[data-prep-preview]");
  if (!preview) {
    return;
  }
  const segments = readPreparationSegments(form);
  const errors = validatePreparationSegments(form, segments);
  const grouped = new Map();
  segments.forEach((segment) => {
    if (!grouped.has(segment.pinCount)) {
      grouped.set(segment.pinCount, { quantity: 0, designators: [] });
    }
    const group = grouped.get(segment.pinCount);
    group.quantity += 1;
    group.designators.push(segment.designators.join("+"));
  });

  const lines = Array.from(grouped.entries())
    .map(([pinCount, group]) => `
      <span class="prep-preview-line">
        <strong>${pinCount} PIN</strong>
        <span>${group.quantity} szt.</span>
        <em>${escapeHtml(group.designators.join(" | "))}</em>
      </span>
    `)
    .join("");
  preview.innerHTML = `
    <strong>Po zapisie</strong>
    <div class="prep-preview-lines">${lines || "<span>Brak odcinków.</span>"}</div>
    ${errors.length ? `<em>${escapeHtml(errors.join(" | "))}</em>` : ""}
  `;
}

async function splitPreparationLine(form) {
  if (!state.selectedProject) {
    alert("Najpierw wybierz projekt.");
    return;
  }
  const segments = readPreparationSegments(form);
  const errors = validatePreparationSegments(form, segments);
  if (errors.length) {
    alert(errors.join("\n"));
    return;
  }

  const response = await api(`/api/projects/${state.selectedProject.id}/steps/${form.dataset.stepId}/split-pins`, {
    method: "POST",
    body: JSON.stringify({
      segments,
      technologyNote: form.elements.technologyNote.value,
    }),
  });
  state.selectedProject = response.project;
  await loadProjects();
  await selectProject(response.project.id, "preparation");
}

async function markPreparationNotNeeded(form) {
  if (!state.selectedProject) {
    alert("Najpierw wybierz projekt.");
    return;
  }
  const confirmed = window.confirm("Oznaczyć tę linię jako niewymagającą przygotowania?\n\nLinia zostanie bez zmian w montażu, ale zniknie z listy przygotowania.");
  if (!confirmed) {
    return;
  }
  const response = await api(`/api/projects/${state.selectedProject.id}/steps/${form.dataset.stepId}/no-preparation`, {
    method: "POST",
    body: JSON.stringify({
      reason: "fałszywy kandydat",
    }),
  });
  state.selectedProject = response.project;
  await loadProjects();
  await selectProject(response.project.id, "preparation");
}

async function consolidatePinSteps() {
  if (!state.selectedProject) {
    alert("Najpierw wybierz projekt.");
    return;
  }
  const response = await api(`/api/projects/${state.selectedProject.id}/consolidate-pin-steps`, {
    method: "POST",
  });
  state.selectedProject = response.project;
  await loadProjects();
  await selectProject(response.project.id, "lines");
}

async function saveStepNotes(form) {
  if (!state.selectedProject) {
    alert("Najpierw wybierz projekt.");
    return;
  }
  const response = await api(`/api/projects/${state.selectedProject.id}/steps/${form.dataset.stepId}/notes`, {
    method: "POST",
    body: JSON.stringify({
      notes: form.elements.notes.value,
    }),
  });
  state.selectedProject = response.project;
  await loadProjects();
  await selectProject(response.project.id, "lines");
}

async function skipStep(stepId) {
  if (!state.selectedProject) {
    alert("Najpierw wybierz projekt.");
    return;
  }
  const reason = window.prompt("Powód pominięcia tej linii:", "decyzja technologiczna");
  if (reason === null) {
    return;
  }
  const response = await api(`/api/projects/${state.selectedProject.id}/steps/${stepId}/skip`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
  state.selectedProject = response.project;
  await loadProjects();
  await selectProject(response.project.id, "lines");
}

async function deleteStep(stepId) {
  if (!state.selectedProject) {
    alert("Najpierw wybierz projekt.");
    return;
  }
  const confirmed = window.confirm("Usunąć tę linię z projektu?\n\nLinia zniknie z montażu i zostaną przeliczone numery kroków.");
  if (!confirmed) {
    return;
  }
  const response = await api(`/api/projects/${state.selectedProject.id}/steps/${stepId}`, {
    method: "DELETE",
  });
  state.selectedProject = response.project;
  await loadProjects();
  await selectProject(response.project.id, "lines");
}

function checkedProUnitIndexes() {
  return Array.from(els.projectDetails.querySelectorAll("[data-pro-unit-index]:checked"))
    .map((input) => Number(input.dataset.proUnitIndex))
    .filter((index) => Number.isFinite(index));
}

async function runProAction(action) {
  try {
    await action();
  } catch (error) {
    alert(error.message || String(error));
  }
}

function attachLineProTools() {
  if (!state.selectedProject || state.activeProjectTab !== "lines") {
    return;
  }
  els.projectDetails.querySelectorAll("[data-line-select]").forEach((input) => {
    input.addEventListener("change", () => {
      const stepId = Number(input.dataset.lineSelect);
      if (input.checked) {
        state.selectedLineIds.add(stepId);
      } else {
        state.selectedLineIds.delete(stepId);
      }
      renderProjectDetails();
    });
  });
  els.projectDetails.querySelectorAll("[data-open-pro-editor]").forEach((button) => {
    button.addEventListener("click", () => {
      state.proEditorStepId = Number(button.dataset.openProEditor);
      renderProjectDetails();
    });
  });
  els.projectDetails.querySelector("[data-close-pro-editor]")?.addEventListener("click", () => {
    state.proEditorStepId = null;
    renderProjectDetails();
  });
  els.projectDetails.querySelector("[data-clear-line-selection]")?.addEventListener("click", () => {
    state.selectedLineIds.clear();
    renderProjectDetails();
  });
  els.projectDetails.querySelector("[data-merge-selected-steps]")?.addEventListener("click", () => runProAction(mergeSelectedSteps));
  els.projectDetails.querySelector("[data-merge-selected-steps-mixed]")?.addEventListener("click", () => runProAction(() => mergeSelectedSteps(true)));
  els.projectDetails.querySelectorAll("[data-step-reorder]").forEach((button) => {
    button.addEventListener("click", () => runProAction(() => reorderStep(button.dataset.stepReorder, button.dataset.direction)));
  });
  els.projectDetails.querySelectorAll("[data-unskip-step]").forEach((button) => {
    button.addEventListener("click", () => runProAction(() => unskipStep(button.dataset.unskipStep)));
  });
  els.projectDetails.querySelectorAll("[data-pro-step-details-form]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      runProAction(() => saveProStepDetails(form));
    });
  });
  els.projectDetails.querySelectorAll("[data-pro-split-units]").forEach((button) => {
    button.addEventListener("click", () => runProAction(() => splitProUnits(button.dataset.proSplitUnits)));
  });
  els.projectDetails.querySelectorAll("[data-pro-move-units]").forEach((button) => {
    button.addEventListener("click", () => runProAction(() => moveProUnits(button.dataset.proMoveUnits)));
  });
}

async function saveProStepDetails(form) {
  if (!state.selectedProject) {
    return;
  }
  const data = formData(form);
  const response = await api(`/api/projects/${state.selectedProject.id}/steps/${form.dataset.stepId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
  state.selectedProject = response.project;
  await loadProjects();
  await selectProject(response.project.id, "lines");
}

async function mergeSelectedSteps(allowMixed = false) {
  if (!state.selectedProject) {
    return;
  }
  const stepIds = selectedLineIdsForProject(state.selectedProject);
  if (stepIds.length < 2) {
    alert("Zaznacz przynajmniej dwie linie.");
    return;
  }
  if (allowMixed) {
    const confirmed = window.confirm(`Scali\u0107 technologicznie ${stepIds.length} zaznaczone linie?\n\nPierwsza/najwy\u017csza zaznaczona linia zostanie baz\u0105 warto\u015bci i indeksu. Pozosta\u0142e opisy trafi\u0105 do uwag technologicznych.`);
    if (!confirmed) {
      return;
    }
    const response = await api(`/api/projects/${state.selectedProject.id}/steps/merge`, {
      method: "POST",
      body: JSON.stringify({ stepIds, allowMixed: true }),
    });
    state.selectedLineIds.clear();
    state.proEditorStepId = null;
    state.selectedProject = response.project;
    await loadProjects();
    await selectProject(response.project.id, "lines");
    return;
  }
  const confirmed = window.confirm(`Scalić ${stepIds.length} zaznaczone linie?\n\nScalanie działa tylko dla tej samej wartości i indeksu Medcom.`);
  if (!confirmed) {
    return;
  }
  const response = await api(`/api/projects/${state.selectedProject.id}/steps/merge`, {
    method: "POST",
    body: JSON.stringify({ stepIds }),
  });
  state.selectedLineIds.clear();
  state.proEditorStepId = null;
  state.selectedProject = response.project;
  await loadProjects();
  await selectProject(response.project.id, "lines");
}

async function reorderStep(stepId, direction) {
  if (!state.selectedProject) {
    return;
  }
  const response = await api(`/api/projects/${state.selectedProject.id}/steps/${stepId}/reorder`, {
    method: "POST",
    body: JSON.stringify({ direction }),
  });
  state.selectedProject = response.project;
  await loadProjects();
  await selectProject(response.project.id, "lines");
}

async function unskipStep(stepId) {
  if (!state.selectedProject) {
    return;
  }
  const response = await api(`/api/projects/${state.selectedProject.id}/steps/${stepId}/unskip`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  state.selectedProject = response.project;
  await loadProjects();
  await selectProject(response.project.id, "lines");
}

async function splitProUnits(stepId) {
  if (!state.selectedProject) {
    return;
  }
  const unitIndexes = checkedProUnitIndexes();
  if (!unitIndexes.length) {
    alert("Zaznacz sztuki/odcinki do rozdzielenia.");
    return;
  }
  const response = await api(`/api/projects/${state.selectedProject.id}/steps/${stepId}/split-units`, {
    method: "POST",
    body: JSON.stringify({ unitIndexes }),
  });
  state.selectedProject = response.project;
  await loadProjects();
  await selectProject(response.project.id, "lines");
}

async function moveProUnits(stepId) {
  if (!state.selectedProject) {
    return;
  }
  const unitIndexes = checkedProUnitIndexes();
  const targetStepId = els.projectDetails.querySelector("[data-pro-move-target]")?.value || "";
  if (!unitIndexes.length) {
    alert("Zaznacz sztuki/odcinki do przeniesienia.");
    return;
  }
  if (!targetStepId) {
    alert("Wybierz linię docelową.");
    return;
  }
  const response = await api(`/api/projects/${state.selectedProject.id}/steps/${stepId}/move-units`, {
    method: "POST",
    body: JSON.stringify({ unitIndexes, targetStepId }),
  });
  state.selectedProject = response.project;
  await loadProjects();
  await selectProject(response.project.id, "lines");
}

async function releaseProjectToOperator() {
  if (!state.selectedProject) {
    alert("Najpierw wybierz projekt.");
    return;
  }
  const readiness = projectReadiness(state.selectedProject);
  if (!readiness.ready) {
    alert(`Projekt nie jest gotowy do operatora.\n\nBlokady:\n${readiness.blockers.map((item) => `- ${item.label}: ${item.detail}`).join("\n")}`);
    return;
  }
  const confirmed = window.confirm(`Przekazać projekt "${state.selectedProject.name}" do operatora?\n\nPo przekazaniu pojawi się na liście startu sesji operatora.`);
  if (!confirmed) {
    return;
  }
  const response = await api(`/api/projects/${state.selectedProject.id}`, {
    method: "PUT",
    body: JSON.stringify({
      name: state.selectedProject.name,
      boardWidth: state.selectedProject.board_width,
      boardHeight: state.selectedProject.board_height,
      status: "ready",
    }),
  });
  state.selectedProject = response.project;
  await loadProjects();
  await selectProject(response.project.id, "summary");
}

async function setProjectStatus(status) {
  if (!state.selectedProject) {
    alert("Najpierw wybierz projekt.");
    return;
  }
  const cleanStatus = String(status || "").trim();
  if (!cleanStatus) {
    return;
  }
  const readiness = projectReadiness(state.selectedProject);
  if (cleanStatus === "ready" && !readiness.ready) {
    alert(`Projekt nie jest gotowy do operatora.\n\nBlokady:\n${readiness.blockers.map((item) => `- ${item.label}: ${item.detail}`).join("\n")}`);
    return;
  }
  const messages = {
    ready: {
      question: `Oznaczyc projekt "${state.selectedProject.name}" jako OK dla operatora?`,
      detail: "Po zapisie projekt pojawi sie na liscie Operatora.",
    },
    prepared: {
      question: `Cofnac projekt "${state.selectedProject.name}" z listy Operatora?`,
      detail: "Projekt zostanie w Adminie jako Przygotowany i zniknie operatorowi.",
    },
    archived: {
      question: `Zarchiwizowac projekt "${state.selectedProject.name}"?`,
      detail: "Projekt nie bedzie widoczny dla Operatora.",
    },
  };
  const message = messages[cleanStatus] || {
    question: `Zmienic status projektu "${state.selectedProject.name}" na ${statusLabel(cleanStatus)}?`,
    detail: "Zmiana statusu zostanie zapisana w projekcie.",
  };
  if (!window.confirm(`${message.question}\n\n${message.detail}`)) {
    return;
  }
  const response = await api(`/api/projects/${state.selectedProject.id}`, {
    method: "PUT",
    body: JSON.stringify({
      name: state.selectedProject.name,
      boardWidth: state.selectedProject.board_width,
      boardHeight: state.selectedProject.board_height,
      status: cleanStatus,
    }),
  });
  state.selectedProject = response.project;
  await loadProjects();
  await selectProject(response.project.id, "summary");
}

function stepSegments(step) {
  if (Array.isArray(step.segments) && step.segments.length) {
    return step.segments.map((segment) => ({
      pinCount: Number(segment.pinCount) || extractPinCount(step.value, 1),
      designators: Array.isArray(segment.designators) ? segment.designators : splitDesignators(segment.label || ""),
      label: segment.label || (Array.isArray(segment.designators) ? segment.designators.join("+") : ""),
      quantity: Number(segment.quantity) || 1,
    }));
  }

  const notes = String(step.notes || "");
  const match = notes.match(/Odcinki:\s*(.+)$/i);
  if (!match) {
    return [];
  }
  const labels = match[1]
    .split(";")
    .map((label) => label.trim())
    .filter(Boolean);
  const counts = pinCountsFromValue(step.value);
  const useInnerPinCount = labels.length
    && counts.length > 1
    && counts[0] === 1
    && counts[1] > 1
    && labels.every((label) => splitDesignators(label.replaceAll("+", ",")).length === 1);
  const pinCount = useInnerPinCount ? counts[1] : (counts[0] || 1);
  return labels.map((label) => ({
      pinCount,
      designators: splitDesignators(label.replaceAll("+", ",")),
      label,
      quantity: 1,
    }));
}

function stepNotesWithoutSegments(step) {
  return String(step.notes || "").replace(/\s*\|\s*Odcinki:\s*.+$/i, "");
}

function stepPinCount(step) {
  const counts = pinCountsFromValue(step.value);
  if (!counts.length) {
    return 0;
  }
  const segments = stepSegments(step);
  const canUseOriginalInnerValue = segments.length
    && counts.length > 1
    && counts[0] === 1
    && counts[1] > 1
    && segments.every((segment) => (segment.designators || []).length === 1);
  return canUseOriginalInnerValue ? counts[1] : counts[0];
}

function renderStepValue(step) {
  const rawValue = String(step.value || "");
  const counts = pinCountsFromValue(rawValue);
  const pinCount = stepPinCount(step);
  if (pinCount && counts.length > 1 && counts[0] !== pinCount) {
    return rawValue.replace(/^\s*\d+\s*PIN/i, `${pinCount} PIN`);
  }
  return rawValue;
}

function renderStepPieces(step) {
  const segments = stepSegments(step);
  if (!segments.length) {
    return escapeHtml(step.designators);
  }
  return `
    <div class="segment-list">
      ${segments.map((segment) => `<span class="segment-pill">${escapeHtml(segment.label || segment.designators.join("+"))}</span>`).join("")}
    </div>
  `;
}

function renderStepQuantity(step) {
  const segments = stepSegments(step);
  if (!segments.length) {
    return `${step.quantity}`;
  }
  const quantity = segments.reduce((total, segment) => total + (Number(segment.quantity) || 1), 0);
  const pinCount = stepPinCount(step);
  const suffix = pinCount ? ` po ${pinCount} PIN` : "";
  return `${quantity} szt.${suffix}`;
}

function stepUnitsForPro(step) {
  const segments = stepSegments(step);
  if (segments.length) {
    return segments.map((segment, index) => ({
      index,
      label: segment.label || (segment.designators || []).join("+"),
      designators: segment.designators || [],
      quantity: Number(segment.quantity) || 1,
      pinCount: Number(segment.pinCount) || 0,
    }));
  }
  return splitDesignators(step.designators).map((designator, index) => ({
    index,
    label: designator,
    designators: [designator],
    quantity: 1,
    pinCount: 0,
  }));
}

function selectedLineIdsForProject(project) {
  const validIds = new Set((project.steps || []).map((step) => Number(step.id)));
  state.selectedLineIds = new Set([...state.selectedLineIds].filter((stepId) => validIds.has(Number(stepId))));
  return [...state.selectedLineIds];
}

function renderLineProEditor(project) {
  const step = (project.steps || []).find((item) => Number(item.id) === Number(state.proEditorStepId));
  if (!step) {
    return "";
  }
  const notes = stepNotesWithoutSegments(step);
  const units = stepUnitsForPro(step);
  const targetOptions = (project.steps || [])
    .filter((item) => Number(item.id) !== Number(step.id))
    .map((item) => {
      const sameValue = String(renderStepValue(item)).trim().toUpperCase() === String(renderStepValue(step)).trim().toUpperCase();
      const sameIndex = normalizeMedcomIndex(item.medcom_index) === normalizeMedcomIndex(step.medcom_index);
      const disabled = sameValue && sameIndex ? "" : "disabled";
      return `<option value="${item.id}" ${disabled}>${item.step_no}. ${escapeHtml(renderStepValue(item))} | ${escapeHtml(item.designators)}</option>`;
    })
    .join("");

  return `
    <section class="pro-editor">
      <div class="pro-editor-head">
        <div>
          <strong>Edycja PRO linii ${step.step_no}</strong>
          <span>${escapeHtml(renderStepValue(step))} | ${escapeHtml(step.medcom_index || "-")}</span>
        </div>
        <button type="button" data-close-pro-editor>Zamknij</button>
      </div>
      <form class="pro-details-form" data-pro-step-details-form data-step-id="${step.id}">
        <label>
          Wartość
          <input name="value" value="${escapeHtml(renderStepValue(step))}" required>
        </label>
        <label>
          Indeks Medcom
          <input name="medcomIndex" value="${escapeHtml(step.medcom_index || "")}">
        </label>
        <label>
          Ilość
          <input name="quantity" type="number" min="1" value="${escapeHtml(renderStepQuantity(step).match(/^\\d+/)?.[0] || step.quantity || 1)}">
        </label>
        <label class="pro-notes-field">
          Uwagi technologiczne
          <input name="notes" value="${escapeHtml(notes)}">
        </label>
        <button type="submit" class="primary">Zapisz opis linii</button>
      </form>
      <div class="pro-unit-tools">
        <div>
          <strong>Sztuki / odcinki w tej linii</strong>
          <span>Zaznacz elementy, które mają iść osobno albo do innej linii.</span>
        </div>
        <div class="pro-unit-list">
          ${units.map((unit) => `
            <label class="pro-unit">
              <input type="checkbox" data-pro-unit-index="${unit.index}">
              <span>${escapeHtml(unit.label)}</span>
              <em>${escapeHtml((unit.designators || []).join(","))}${unit.pinCount ? ` | ${unit.pinCount} PIN` : ""}</em>
            </label>
          `).join("")}
        </div>
        <div class="pro-actions-row">
          <button type="button" data-pro-split-units="${step.id}">Rozdziel zaznaczone do nowej linii</button>
          <label>
            Przenieś do
            <select data-pro-move-target>
              <option value="">Wybierz linię...</option>
              ${targetOptions}
            </select>
          </label>
          <button type="button" data-pro-move-units="${step.id}">Przenieś zaznaczone</button>
        </div>
      </div>
    </section>
  `;
}

function renderLinesTab(project) {
  const rows = (project.steps || [])
    .map((step) => {
      const notes = stepNotesWithoutSegments(step);
      return `
      <tr class="${stepIsSkipped(step) ? "line-skipped" : ""}">
        <td class="num">${step.step_no}</td>
        <td>${renderStepPieces(step)}</td>
        <td>${escapeHtml(renderStepValue(step))}</td>
        <td>${escapeHtml(step.medcom_index || "")}</td>
        <td>${escapeHtml(renderStepQuantity(step))}</td>
        <td>
          <form class="line-note-form" data-step-notes-form data-step-id="${step.id}">
            <input name="notes" value="${escapeHtml(notes)}" placeholder="Uwagi technologiczne">
            <button type="submit">Zapisz</button>
          </form>
        </td>
        <td class="num">${step.seconds ?? ""}</td>
        <td>
          <div class="line-actions">
            ${stepHasMissingPoint(step) ? '<span class="badge missing-point-badge">Brak P&amp;P</span>' : ""}
            ${stepIsSkipped(step) ? '<span class="badge skipped-badge">Pominięta</span>' : `<button type="button" data-skip-step="${step.id}">Pomiń</button>`}
            <button type="button" class="danger" data-delete-step="${step.id}">Usuń</button>
          </div>
        </td>
      </tr>
    `;
    })
    .join("");

  return `
    <div class="table-actions">
      <button type="button" data-panel="addLine">Dodaj linię</button>
      <button type="button" data-consolidate-pins>Scal identyczne odcinki</button>
    </div>
    <div class="table-wrap">
      <table class="admin-table">
        <thead>
          <tr>
            <th>Lp.</th>
            <th>Sztuki / odcinki</th>
            <th>Wartość</th>
            <th>Indeks Medcom</th>
            <th>Ilość</th>
            <th>Uwagi</th>
            <th>Sekundy</th>
            <th>Akcje</th>
          </tr>
        </thead>
        <tbody>
          ${rows || '<tr><td colspan="8" class="muted">Projekt nie ma jeszcze linii.</td></tr>'}
        </tbody>
      </table>
    </div>
  `;
}

function renderLinesTabPro(project) {
  const selectedIds = selectedLineIdsForProject(project);
  const selectedCount = selectedIds.length;
  const rows = (project.steps || [])
    .map((step) => {
      const notes = stepNotesWithoutSegments(step);
      const selected = state.selectedLineIds.has(Number(step.id));
      const editing = Number(state.proEditorStepId) === Number(step.id);
      return `
      <tr class="${stepIsSkipped(step) ? "line-skipped" : ""} ${editing ? "line-editing" : ""}">
        <td class="line-select-cell"><input type="checkbox" data-line-select="${step.id}" ${selected ? "checked" : ""}></td>
        <td class="num">${step.step_no}</td>
        <td>${renderStepPieces(step)}</td>
        <td>${escapeHtml(renderStepValue(step))}</td>
        <td>${escapeHtml(step.medcom_index || "")}</td>
        <td>${escapeHtml(renderStepQuantity(step))}</td>
        <td>
          <form class="line-note-form" data-step-notes-form data-step-id="${step.id}">
            <input name="notes" value="${escapeHtml(notes)}" placeholder="Uwagi technologiczne">
            <button type="submit">Zapisz</button>
          </form>
        </td>
        <td class="num">${step.seconds ?? ""}</td>
        <td>
          <div class="line-actions">
            ${stepHasMissingPoint(step) ? '<span class="badge missing-point-badge">Brak P&amp;P</span>' : ""}
            <button type="button" data-open-admin-preview-step="${step.id}">Podgl\u0105d</button>
            <button type="button" data-open-pro-editor="${step.id}">PRO</button>
            <button type="button" data-step-reorder="${step.id}" data-direction="up">↑</button>
            <button type="button" data-step-reorder="${step.id}" data-direction="down">↓</button>
            ${stepIsSkipped(step) ? `<button type="button" data-unskip-step="${step.id}">Przywróć</button>` : `<button type="button" data-skip-step="${step.id}">Pomiń</button>`}
            <button type="button" class="danger" data-delete-step="${step.id}">Usuń</button>
          </div>
        </td>
      </tr>
    `;
    })
    .join("");

  return `
    <div class="table-actions">
      <div class="pro-bulk-actions">
        <button type="button" data-panel="addLine">Dodaj linię</button>
        <button type="button" data-consolidate-pins>Scal identyczne odcinki</button>
        <button type="button" data-merge-selected-steps ${selectedCount >= 2 ? "" : "disabled"}>Scal zaznaczone (${selectedCount})</button>
        <button type="button" data-merge-selected-steps-mixed ${selectedCount >= 2 ? "" : "disabled"}>Scal technologicznie (${selectedCount})</button>
        <button type="button" data-clear-line-selection ${selectedCount ? "" : "disabled"}>Wyczyść wybór</button>
      </div>
      <span class="muted">PRO: zaznacz linie albo otwórz edycję konkretnej pozycji.</span>
    </div>
    ${renderLineProEditor(project)}
    <div class="table-wrap">
      <table class="admin-table">
        <thead>
          <tr>
            <th></th>
            <th>Lp.</th>
            <th>Sztuki / odcinki</th>
            <th>Wartość</th>
            <th>Indeks Medcom</th>
            <th>Ilość</th>
            <th>Uwagi</th>
            <th>Sekundy</th>
            <th>Akcje</th>
          </tr>
        </thead>
        <tbody>
          ${rows || '<tr><td colspan="9" class="muted">Projekt nie ma jeszcze linii.</td></tr>'}
        </tbody>
      </table>
    </div>
  `;
}

function normalizeAdminPreviewView(view = {}) {
  const defaults = defaultAdminPreviewView();
  return {
    zoom: clampOperatorZoom(view.zoom || defaults.zoom),
    rotation: normalizeViewRotation(view.rotation),
    markerPalette: normalizeMarkerPalette(view.markerPalette),
    showAllPoints: Boolean(view.showAllPoints),
    showLabels: view.showLabels !== false,
    showPolarity: Boolean(view.showPolarity),
    showContours: view.showContours !== false,
  };
}

function updateAdminPreviewView(patch) {
  state.adminPreviewView = normalizeAdminPreviewView({
    ...state.adminPreviewView,
    ...patch,
  });
  renderProjectDetails();
}

function adminPreviewStepMatches(step, query) {
  const cleanQuery = String(query || "").trim().toUpperCase();
  if (!cleanQuery) {
    return true;
  }
  const haystack = [
    step.step_no,
    renderStepValue(step),
    step.medcom_index,
    renderStepQuantity(step),
    stepDesignatorsForPoints(step).join(","),
    stepNotesWithoutSegments(step),
  ].join(" ").toUpperCase();
  return haystack.includes(cleanQuery);
}

function adminPreviewSteps(project) {
  const steps = project.steps || [];
  const cleanQuery = String(state.adminPreviewSearch || "").trim().toUpperCase();
  if (cleanQuery) {
    const exactDesignatorMatches = steps.filter((step) => stepDesignatorsForPoints(step).some((designator) => designator === cleanQuery));
    if (exactDesignatorMatches.length) {
      return exactDesignatorMatches;
    }
  }
  const filtered = steps.filter((step) => adminPreviewStepMatches(step, state.adminPreviewSearch));
  return filtered.length ? filtered : steps;
}

function adminPreviewCurrentStep(project) {
  const steps = adminPreviewSteps(project);
  if (!steps.length) {
    return null;
  }
  const active = steps.find((step) => Number(step.id) === Number(state.adminPreviewStepId));
  const next = active || steps[0];
  state.adminPreviewStepId = next.id;
  return next;
}

function renderAdminPreviewTab(project) {
  if (!project.steps?.length) {
    return '<div class="empty-state"><strong>Brak linii</strong><span>Zaimportuj BOM/P&amp;P, aby podejrze\u0107 widok operatora.</span></div>';
  }
  if (!project.board_image_path) {
    return '<div class="empty-state"><strong>Brak obrazu PCB</strong><span>Dodaj obraz PCB, aby podejrze\u0107 pozycje na p\u0142ytce.</span></div>';
  }

  const view = normalizeAdminPreviewView(state.adminPreviewView);
  const currentStep = adminPreviewCurrentStep(project);
  const steps = adminPreviewSteps(project);
  const activePoints = currentStep ? pointsForStep(project, currentStep) : [];
  const visiblePoints = view.showAllPoints ? (project.points || []) : activePoints;
  const activeDesignators = activePoints.map((point) => String(point.designator || "").toUpperCase());
  const currentPolarity = view.showPolarity && currentStep ? polarityItemsForStep(project, currentStep) : [];
  const previewContours = view.showContours
    ? (view.showAllPoints ? projectContours(project) : (currentStep ? contoursForStep(project, currentStep) : []))
    : [];
  const missing = currentStep
    ? stepDesignatorsForPoints(currentStep).filter((designator) => !activePoints.some((point) => String(point.designator || "").toUpperCase() === designator))
    : [];

  return `
    <div class="admin-preview-layout" data-admin-preview-root>
      <section class="admin-preview-board">
        <div class="admin-preview-toolbar">
          <label class="admin-preview-search">
            Znajd\u017a
            <input data-admin-preview-search value="${escapeHtml(state.adminPreviewSearch)}" placeholder="np. J1, C7, indeks, warto\u015b\u0107">
          </label>
          <label class="operator-zoom-control">
            <span>Rozmiar</span>
            <input type="range" min="35" max="240" step="5" value="${view.zoom}" data-admin-preview-zoom>
            <strong>${view.zoom}%</strong>
          </label>
          <div class="operator-segment">
            <span>Obr\u00f3t</span>
            ${[0, 90, 180, 270].map((rotation) => `
              <button type="button" class="${view.rotation === rotation ? "active" : ""}" data-admin-preview-rotation="${rotation}">${rotation}</button>
            `).join("")}
          </div>
          <button type="button" data-admin-preview-center>Centruj</button>
          <button type="button" class="${view.showAllPoints ? "active" : ""}" data-admin-preview-toggle-points>Reszta: ${view.showAllPoints ? "ON" : "OFF"}</button>
          <button type="button" class="${view.showLabels ? "active" : ""}" data-admin-preview-toggle-labels>Opisy: ${view.showLabels ? "ON" : "OFF"}</button>
          <button type="button" class="${view.showPolarity ? "active" : ""}" data-admin-preview-toggle-polarity>Polaryzacja: ${view.showPolarity ? "ON" : "OFF"}</button>
          <button type="button" class="${view.showContours ? "active" : ""}" data-admin-preview-toggle-contours>Kontury: ${view.showContours ? "ON" : "OFF"}</button>
        </div>
        ${renderBoardMap(project, visiblePoints, {
          selectedDesignators: activeDesignators.length ? activeDesignators : ["__NO_ACTIVE_POINT__"],
          showSoftPoints: view.showAllPoints,
          showLabels: view.showLabels,
          markerClass: "operator-board-marker",
          markerPalette: view.markerPalette,
          viewRotation: view.rotation,
          zoomPercent: view.zoom,
          operatorStage: true,
          polarityItems: currentPolarity,
          contours: previewContours,
          showSoftContours: view.showAllPoints,
        })}
      </section>
      <aside class="admin-preview-panel">
        ${currentStep ? `
          <div class="admin-preview-current">
            <span>Linia ${currentStep.step_no}</span>
            <strong>${escapeHtml(renderStepValue(currentStep))}</strong>
            <em>${escapeHtml(currentStep.medcom_index || "-")} | ${escapeHtml(renderStepQuantity(currentStep))}</em>
            <div>${renderStepPieces(currentStep)}</div>
            ${missing.length ? `<p>Bez punktu P&amp;P: ${escapeHtml(missing.join(", "))}</p>` : ""}
            ${stepNotesWithoutSegments(currentStep) ? `<p>${escapeHtml(stepNotesWithoutSegments(currentStep))}</p>` : ""}
          </div>
        ` : ""}
        <div class="table-wrap admin-preview-list">
          <table class="admin-table">
            <thead>
              <tr>
                <th>Lp.</th>
                <th>Desygnatory</th>
                <th>Warto\u015b\u0107</th>
              </tr>
            </thead>
            <tbody>
              ${steps.map((step) => `
                <tr class="${Number(step.id) === Number(currentStep?.id) ? "active" : ""}" data-admin-preview-step="${step.id}">
                  <td>${step.step_no}</td>
                  <td>${renderStepPieces(step)}</td>
                  <td>${escapeHtml(renderStepValue(step))}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      </aside>
    </div>
  `;
}

function adminPreviewActiveMarkers(root) {
  return Array.from(root.querySelectorAll('[data-board-marker="active"], .polarity-plus-marker.active'));
}

function centerAdminPreviewOnCurrent() {
  const root = els.projectDetails.querySelector("[data-admin-preview-root]");
  const stage = root?.querySelector("[data-operator-board-stage]");
  const activeMarkers = root ? adminPreviewActiveMarkers(root) : [];
  if (!stage || !activeMarkers.length) {
    return;
  }
  const bounds = operatorStageMarkerBounds(stage, activeMarkers);
  const centerX = (bounds.left + bounds.right) / 2;
  const centerY = (bounds.top + bounds.bottom) / 2;
  stage.scrollTo({
    left: clampScroll(centerX - stage.clientWidth / 2, stage.scrollWidth - stage.clientWidth),
    top: clampScroll(centerY - stage.clientHeight / 2, stage.scrollHeight - stage.clientHeight),
    behavior: "auto",
  });
}

function scheduleAdminPreviewCenter() {
  requestAnimationFrame(() => {
    requestAnimationFrame(centerAdminPreviewOnCurrent);
  });
}

function attachAdminPreviewTools() {
  if (!state.selectedProject || state.activeProjectTab !== "preview") {
    return;
  }
  const root = els.projectDetails.querySelector("[data-admin-preview-root]");
  if (!root) {
    return;
  }
  root.querySelector("[data-admin-preview-search]")?.addEventListener("input", (event) => {
    state.adminPreviewSearch = event.target.value;
    state.adminPreviewStepId = null;
    renderProjectDetails();
  });
  root.querySelector("[data-admin-preview-zoom]")?.addEventListener("input", (event) => {
    updateAdminPreviewView({ zoom: Number(event.target.value) });
  });
  root.querySelectorAll("[data-admin-preview-rotation]").forEach((button) => {
    button.addEventListener("click", () => updateAdminPreviewView({ rotation: Number(button.dataset.adminPreviewRotation) }));
  });
  root.querySelector("[data-admin-preview-toggle-points]")?.addEventListener("click", () => {
    updateAdminPreviewView({ showAllPoints: !state.adminPreviewView.showAllPoints });
  });
  root.querySelector("[data-admin-preview-toggle-labels]")?.addEventListener("click", () => {
    updateAdminPreviewView({ showLabels: !state.adminPreviewView.showLabels });
  });
  root.querySelector("[data-admin-preview-toggle-polarity]")?.addEventListener("click", () => {
    updateAdminPreviewView({ showPolarity: !state.adminPreviewView.showPolarity });
  });
  root.querySelector("[data-admin-preview-toggle-contours]")?.addEventListener("click", () => {
    updateAdminPreviewView({ showContours: !state.adminPreviewView.showContours });
  });
  root.querySelector("[data-admin-preview-center]")?.addEventListener("click", centerAdminPreviewOnCurrent);
  root.querySelectorAll("[data-admin-preview-step]").forEach((row) => {
    row.addEventListener("click", () => {
      state.adminPreviewStepId = Number(row.dataset.adminPreviewStep);
      renderProjectDetails();
    });
  });
  const image = root.querySelector("[data-operator-board-stage] img");
  if (image && !image.complete) {
    image.addEventListener("load", scheduleAdminPreviewCenter, { once: true });
  }
  scheduleAdminPreviewCenter();
}

function renderPointsTab(project) {
  const missing = missingPointDesignators(project);
  const missingPanel = missing.length ? `
    <div class="summary-box">
      <strong>Linie bez punktu P&amp;P</strong>
      <span>${escapeHtml(shortList(missing, 30))}</span>
      <span>Wgraj aktualny P&amp;P przez akcj\u0119 "Uzupe\u0142nij punkty P&amp;P", aby dopi\u0105\u0107 brakuj\u0105ce markery bez ruszania linii monta\u017cowych.</span>
    </div>
  ` : "";
  const rows = (project.points || [])
    .map((point) => `
      <tr>
        <td>${escapeHtml(point.designator)}</td>
        <td class="num">${formatNumber(point.x)}</td>
        <td class="num">${formatNumber(point.y)}</td>
        <td class="num">${point.rotation ?? ""}</td>
      </tr>
    `)
    .join("");

  return `
    ${missingPanel}
    <div class="table-wrap">
      <table class="admin-table points-table">
        <thead>
          <tr>
            <th>Desygnator</th>
            <th>X</th>
            <th>Y</th>
            <th>Rotacja</th>
          </tr>
        </thead>
        <tbody>
          ${rows || '<tr><td colspan="4" class="muted">Brak punktów P&amp;P.</td></tr>'}
        </tbody>
      </table>
    </div>
  `;
}

function renderContoursTab(project) {
  const overlay = project.board_contours || {};
  const contours = projectContours(project);
  const assignments = Array.isArray(overlay.assignments) ? overlay.assignments : [];
  const profile = overlay.profile || {};
  const summary = projectContourSummary(project);
  const assignedContours = contours.filter((contour) => contourDesignators(contour).length);
  const previewContours = assignedContours.length ? assignedContours : contours;
  const assignedRows = assignments
    .slice()
    .sort((a, b) => String(a.designator || "").localeCompare(String(b.designator || ""), "pl"))
    .slice(0, 120)
    .map((item) => {
      const contour = contours.find((candidate) => candidate.id === item.contourId);
      const size = contour ? `${formatNumber(contour.width)} x ${formatNumber(contour.height)} mm` : "-";
      return `
        <tr>
          <td>${escapeHtml(item.designator || "-")}</td>
          <td>${escapeHtml(item.contourId || "-")}</td>
          <td>${escapeHtml(size)}</td>
          <td class="num">${Math.round((Number(item.confidence) || 0) * 100)}%</td>
          <td>${escapeHtml(item.mode || "-")}</td>
        </tr>
      `;
    })
    .join("");

  return `
    <div class="gerber-contours-layout">
      <section class="panel gerber-import-panel">
        <h3>Import kontur\u00f3w z Gerber</h3>
        <p class="muted">Wczytaj profil PCB i warstw\u0119 sitodruku. System spr\u00f3buje wykry\u0107 prostok\u0105tne kontury i przypisa\u0107 je do punkt\u00f3w P&amp;P.</p>
        <form data-gerber-contours-form>
          <div class="grid two compact-grid">
            <label>
              Profile / obrys PCB
              <input name="profileGerber" type="file" accept=".gbr,.gbx,.gko,.gk,.gtl,.gts,.gto">
            </label>
            <label>
              Silkscreen Top
              <input name="silkscreenGerber" type="file" accept=".gbr,.gbx,.gko,.gk,.gtl,.gts,.gto" required>
            </label>
          </div>
          <label class="checkbox-row">
            <input name="updateBoardSize" type="checkbox" checked>
            Ustaw wymiary PCB z profile.gbr
          </label>
          <button type="submit" class="primary">Analizuj Gerbery</button>
        </form>
      </section>
      <section class="panel gerber-summary-panel">
        <h3>Wynik</h3>
        ${contours.length ? `
          <div class="summary-grid">
            <span><strong>${summary.contours || contours.length}</strong><em>kontur\u00f3w</em></span>
            <span><strong>${summary.assigned || assignments.length}</strong><em>przypisa\u0144</em></span>
            <span><strong>${formatNumber(profile.width || project.board_width || 0)} x ${formatNumber(profile.height || project.board_height || 0)}</strong><em>profil mm</em></span>
          </div>
        ` : '<p class="muted">Brak zaimportowanych kontur\u00f3w.</p>'}
      </section>
    </div>
    ${project.board_image_path && contours.length ? `
      <div class="gerber-preview-panel">
        ${renderBoardMap(project, [], {
          selectedDesignators: [],
          showSoftPoints: false,
          showLabels: false,
          markerClass: "calibration-marker",
          zoomPercent: 100,
          contours: previewContours,
          showSoftContours: true,
        })}
      </div>
    ` : ""}
    <div class="table-wrap">
      <table class="admin-table">
        <thead>
          <tr>
            <th>Desygnator</th>
            <th>Kontur</th>
            <th>Rozmiar</th>
            <th>Pewno\u015b\u0107</th>
            <th>Tryb</th>
          </tr>
        </thead>
        <tbody>
          ${assignedRows || '<tr><td colspan="5" class="muted">Brak przypisa\u0144 do punkt\u00f3w P&amp;P.</td></tr>'}
        </tbody>
      </table>
    </div>
  `;
}

function renderImageTab(project) {
  if (!project.board_image_path) {
    return '<div class="empty-state"><strong>Brak obrazu PCB</strong><span>Dołącz obraz przy imporcie projektu.</span></div>';
  }
  const view = imageView(project.id);
  return `
    <div class="table-actions">
      <button type="button" data-panel="boardImage">Podmień obraz PCB</button>
      <div class="image-tools">
        <button type="button" data-image-zoom-step="-10">-</button>
        <input data-image-zoom type="range" min="25" max="400" step="5" value="${view.zoom}">
        <strong data-image-zoom-label>${view.zoom}%</strong>
        <span class="image-tool-divider"></span>
        ${[0, 90, 180, 270].map((rotation) => `
          <button type="button" class="${view.rotation === rotation ? "active" : ""}" data-image-rotation="${rotation}">${rotation}</button>
        `).join("")}
        <button type="button" data-image-zoom-step="10">+</button>
        <button type="button" data-image-reset>Reset</button>
      </div>
    </div>
    <div class="image-panel">
      <div class="image-canvas" style="--image-zoom: ${view.zoom / 100}; --image-rotation: ${view.rotation}deg;">
        <img class="pcb-inspection-image" src="${escapeHtml(boardImageUrl(project.board_image_path, project.updated_at))}" alt="Obraz PCB">
      </div>
    </div>
  `;
}

function renderOperatorPreviewsTab(project) {
  const previews = projectPreviewDefinitions(project);
  return `
    <div class="operator-preview-admin">
      <div class="operator-preview-admin-head">
        <div>
          <strong>Podgl\u0105dy widoczne dla operatora</strong>
          <span>Te zdj\u0119cia s\u0105 dodatkow\u0105 pomoc\u0105 technologiczn\u0105, niezale\u017cn\u0105 od mapowania punkt\u00f3w PCB.</span>
        </div>
      </div>
      <div class="operator-preview-admin-grid">
        ${previews.map((preview) => {
          const imageUrl = preview.path ? boardImageUrl(preview.path, project.updated_at) : "";
          const image = preview.path
            ? `
              <a href="${escapeHtml(imageUrl)}" target="_blank" rel="noopener" title="Otw\u00f3rz pe\u0142ny obraz">
                <img src="${escapeHtml(imageUrl)}" alt="${escapeHtml(preview.label)}">
              </a>
            `
            : '<div class="operator-preview-admin-empty">Brak zdj\u0119cia</div>';
          return `
            <section class="operator-preview-admin-card">
              <div>
                <strong>${escapeHtml(preview.label)}</strong>
                <span>${preview.path ? "Zaimportowano" : "Nie dodano"}</span>
              </div>
              <div class="operator-preview-admin-image">
                ${image}
              </div>
            </section>
          `;
        }).join("")}
      </div>
      <form class="operator-preview-admin-form" data-operator-preview-admin-form>
        <div class="grid two compact-grid">
          <label>
            Podgl\u0105d THT
            <input name="thtPreviewImage" type="file" accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp">
          </label>
          <label>
            Podgl\u0105d Oklejanie
            <input name="labelingPreviewImage" type="file" accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp">
          </label>
        </div>
        <div class="form-row">
          <button type="submit" class="primary">Zapisz podgl\u0105dy</button>
          <span class="muted">Mo\u017cesz podmieni\u0107 tylko jedno zdj\u0119cie, drugie zostanie bez zmian.</span>
        </div>
      </form>
    </div>
  `;
}

function imageView(projectId) {
  if (!state.imageViews.has(projectId)) {
    state.imageViews.set(projectId, { zoom: 100, rotation: 0 });
  }
  return state.imageViews.get(projectId);
}

function clampImageZoom(value) {
  return Math.max(25, Math.min(400, Math.round(value / 5) * 5));
}

function updateImageView(projectId, patch) {
  const current = imageView(projectId);
  const next = {
    zoom: clampImageZoom(patch.zoom ?? current.zoom),
    rotation: Number.isFinite(patch.rotation) ? ((patch.rotation % 360) + 360) % 360 : current.rotation,
  };
  state.imageViews.set(projectId, next);
  renderProjectDetails();
}

function attachImageTools() {
  if (!state.selectedProject || state.activeProjectTab !== "image") {
    return;
  }
  const projectId = state.selectedProject.id;
  const zoom = els.projectDetails.querySelector("[data-image-zoom]");
  if (zoom) {
    zoom.addEventListener("input", () => updateImageView(projectId, { zoom: Number(zoom.value) }));
  }
  els.projectDetails.querySelectorAll("[data-image-zoom-step]").forEach((button) => {
    button.addEventListener("click", () => {
      const current = imageView(projectId);
      updateImageView(projectId, { zoom: current.zoom + Number(button.dataset.imageZoomStep || 0) });
    });
  });
  els.projectDetails.querySelectorAll("[data-image-rotation]").forEach((button) => {
    button.addEventListener("click", () => updateImageView(projectId, { rotation: Number(button.dataset.imageRotation) }));
  });
  const reset = els.projectDetails.querySelector("[data-image-reset]");
  if (reset) {
    reset.addEventListener("click", () => updateImageView(projectId, { zoom: 100, rotation: 0 }));
  }
}

function attachOperatorPreviewAdminTools() {
  if (!state.selectedProject || state.activeProjectTab !== "operatorPreviews") {
    return;
  }
  const form = els.projectDetails.querySelector("[data-operator-preview-admin-form]");
  if (!form) {
    return;
  }
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formDataValue = new FormData(form);
    const hasFile = Array.from(formDataValue.values()).some((value) => value instanceof File && value.size > 0);
    if (!hasFile) {
      alert("Wybierz przynajmniej jedno zdj\u0119cie podgl\u0105du.");
      return;
    }
    try {
      const response = await apiForm(`/api/projects/${state.selectedProject.id}/preview-images`, formDataValue);
      form.reset();
      await loadProjects();
      await selectProject(response.project.id, "operatorPreviews");
    } catch (error) {
      alert(error.message);
    }
  });
}

function attachGerberContourTools() {
  if (!state.selectedProject || state.activeProjectTab !== "contours") {
    return;
  }
  const form = els.projectDetails.querySelector("[data-gerber-contours-form]");
  if (!form) {
    return;
  }
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector('button[type="submit"]');
    const previousText = submit?.textContent || "";
    if (submit) {
      submit.disabled = true;
      submit.textContent = "Analizuj\u0119...";
    }
    try {
      const response = await apiForm(`/api/projects/${state.selectedProject.id}/gerber-contours`, new FormData(form));
      state.selectedProject = response.project;
      await loadProjects();
      renderProjectDetails();
    } catch (error) {
      alert(error.message);
    } finally {
      if (submit) {
        submit.disabled = false;
        submit.textContent = previousText;
      }
    }
  });
}

function formatCalibrationNumber(value, digits = 2) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return Number(0).toFixed(digits);
  }
  return number.toFixed(digits);
}

function renderCalibrationTab(project) {
  if (!project.board_image_path) {
    return '<div class="empty-state"><strong>Brak obrazu PCB</strong><span>Dodaj obraz, aby skalibrować punkty P&amp;P.</span></div>';
  }
  if (!project.points?.length) {
    return '<div class="empty-state"><strong>Brak punktów P&amp;P</strong><span>Zaimportuj P&amp;P, aby skalibrować podgląd.</span></div>';
  }

  const calibration = activeBoardCalibration(project);
  const savedCalibration = storedBoardCalibration(project);
  const designatorText = calibrationDesignators(project);
  const selectedDesignators = splitDesignators(designatorText);
  const metrics = boardMapMetrics(project, project.points, calibration);
  const isDirty = JSON.stringify(calibration) !== JSON.stringify(savedCalibration);

  return `
    <div class="calibration-layout">
      <div class="calibration-preview">
        ${renderBoardMap(project, project.points, {
          calibration,
          selectedDesignators,
          showSoftPoints: true,
          markerClass: "calibration-marker",
          stageClass: "calibration-stage",
          mapClass: "calibration-map",
        })}
      </div>
      <div class="calibration-panel">
        <div class="summary-box">
          <strong>Transformacja punktów</strong>
          <span>Obrót: ${calibration.rotation}°</span>
          <span>Odbicie X: ${calibration.flipX ? "tak" : "nie"}</span>
          <span>Odbicie Y: ${calibration.flipY ? "tak" : "nie"}</span>
          <span>Korekta X/Y: ${formatCalibrationNumber(calibration.offsetX)}% / ${formatCalibrationNumber(calibration.offsetY)}%</span>
          <span>Skala X/Y: ${formatCalibrationNumber(calibration.scaleX, 3)} / ${formatCalibrationNumber(calibration.scaleY, 3)}</span>
          <span>Mapa: ${formatNumber(metrics.displayWidth)} x ${formatNumber(metrics.displayHeight)} mm</span>
          ${metrics.swapped ? '<span>Auto: wykryto zamienione wymiary PCB.</span>' : ""}
        </div>
        <label>
          Punkty kontrolne
          <input data-calibration-designators value="${escapeHtml(designatorText)}" placeholder="np. X1,X15,X8,JTAG1">
        </label>
        <div class="calibration-selected">
          ${selectedDesignators.map((designator) => `<span>${escapeHtml(designator)}</span>`).join("")}
        </div>
        <div class="calibration-controls">
          <strong>Obrót punktów</strong>
          <div class="segmented-controls">
            ${[0, 90, 180, 270].map((rotation) => `
              <button type="button" class="${calibration.rotation === rotation ? "active" : ""}" data-calibration-rotation="${rotation}">${rotation}°</button>
            `).join("")}
          </div>
          <button type="button" class="${calibration.flipX ? "active" : ""}" data-calibration-toggle="flipX">Odbij X</button>
          <button type="button" class="${calibration.flipY ? "active" : ""}" data-calibration-toggle="flipY">Odbij Y</button>
        </div>
        <div class="calibration-controls">
          <strong>Precyzyjna korekta</strong>
          <div class="calibration-fine-grid">
            <label>
              Przesuń X (%)
              <input type="number" step="0.05" data-calibration-number="offsetX" value="${formatCalibrationNumber(calibration.offsetX)}">
            </label>
            <label>
              Przesuń Y (%)
              <input type="number" step="0.05" data-calibration-number="offsetY" value="${formatCalibrationNumber(calibration.offsetY)}">
            </label>
            <label>
              Skala X
              <input type="number" min="0.2" max="3" step="0.001" data-calibration-number="scaleX" value="${formatCalibrationNumber(calibration.scaleX, 3)}">
            </label>
            <label>
              Skala Y
              <input type="number" min="0.2" max="3" step="0.001" data-calibration-number="scaleY" value="${formatCalibrationNumber(calibration.scaleY, 3)}">
            </label>
          </div>
          <div class="calibration-nudge-grid">
            <button type="button" data-calibration-adjust="offsetX" data-calibration-delta="-0.1">← 0.1%</button>
            <button type="button" data-calibration-adjust="offsetX" data-calibration-delta="0.1">0.1% →</button>
            <button type="button" data-calibration-adjust="offsetY" data-calibration-delta="-0.1">↑ 0.1%</button>
            <button type="button" data-calibration-adjust="offsetY" data-calibration-delta="0.1">0.1% ↓</button>
          </div>
        </div>
        <div class="form-row">
          <button type="button" class="primary" data-save-calibration ${isDirty ? "" : "disabled"}>Zapisz kalibrację</button>
          <button type="button" data-reset-calibration>Reset</button>
        </div>
        <div class="muted">Ustaw tak, aby punkty kontrolne siedziały na tych samych desygnatorach na zdjęciu. Operator dostanie już zapisany wynik.</div>
      </div>
    </div>
  `;
}

function attachCalibrationTools() {
  if (!state.selectedProject || state.activeProjectTab !== "calibration") {
    return;
  }
  const project = state.selectedProject;
  const input = els.projectDetails.querySelector("[data-calibration-designators]");
  if (input) {
    input.addEventListener("input", () => {
      state.calibrationDesignators.set(project.id, input.value);
      renderProjectDetails();
    });
  }
  els.projectDetails.querySelectorAll("[data-calibration-rotation]").forEach((button) => {
    button.addEventListener("click", () => setCalibrationDraft(project, { rotation: Number(button.dataset.calibrationRotation) }));
  });
  els.projectDetails.querySelectorAll("[data-calibration-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.calibrationToggle;
      setCalibrationDraft(project, { [key]: !activeBoardCalibration(project)[key] });
    });
  });
  els.projectDetails.querySelectorAll("[data-calibration-number]").forEach((inputElement) => {
    const commitInput = (render = false) => {
      const key = inputElement.dataset.calibrationNumber;
      const rawValue = String(inputElement.value || "").trim();
      const fallback = key === "scaleX" || key === "scaleY" ? 1 : 0;
      const next = normalizeBoardCalibration({
        ...activeBoardCalibration(project),
        [key]: rawValue ? Number(rawValue) : fallback,
      });
      state.calibrationDrafts.set(project.id, next);
      const saveButton = els.projectDetails.querySelector("[data-save-calibration]");
      if (saveButton) {
        saveButton.disabled = JSON.stringify(next) === JSON.stringify(storedBoardCalibration(project));
      }
      if (render) {
        renderProjectDetails();
      }
    };
    inputElement.addEventListener("input", () => commitInput(false));
    inputElement.addEventListener("change", () => commitInput(true));
    inputElement.addEventListener("blur", () => commitInput(true));
    inputElement.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        commitInput(true);
      }
    });
  });
  els.projectDetails.querySelectorAll("[data-calibration-adjust]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.calibrationAdjust;
      const delta = Number(button.dataset.calibrationDelta) || 0;
      const calibration = activeBoardCalibration(project);
      setCalibrationDraft(project, { [key]: Number(calibration[key] || 0) + delta });
    });
  });
  els.projectDetails.querySelector("[data-reset-calibration]")?.addEventListener("click", () => {
    state.calibrationDrafts.set(project.id, normalizeBoardCalibration({}));
    renderProjectDetails();
  });
  els.projectDetails.querySelector("[data-save-calibration]")?.addEventListener("click", saveCalibration);
}

async function saveCalibration() {
  if (!state.selectedProject) {
    return;
  }
  const projectId = state.selectedProject.id;
  const calibration = activeBoardCalibration(state.selectedProject);
  const response = await api(`/api/projects/${projectId}/calibration`, {
    method: "PUT",
    body: JSON.stringify(calibration),
  });
  state.calibrationDrafts.delete(projectId);
  state.selectedProject = response.project;
  await loadProjects();
  await selectProject(projectId, "calibration");
}

function pointsByDesignator(project) {
  const map = new Map();
  (project.points || []).forEach((point) => {
    map.set(String(point.designator || "").toUpperCase(), point);
  });
  return map;
}

function stepsByDesignator(project) {
  const map = new Map();
  (project.steps || []).forEach((step) => {
    stepDesignatorsForPoints(step).forEach((designator) => {
      if (!map.has(designator)) {
        map.set(designator, step);
      }
    });
  });
  return map;
}

function polarityRows(project) {
  const pointMap = pointsByDesignator(project);
  const stepMap = stepsByDesignator(project);
  return (project.polarity || [])
    .map((item) => ({
      ...item,
      designator: String(item.designator || "").toUpperCase(),
      point: pointMap.get(String(item.designator || "").toUpperCase()) || null,
      step: stepMap.get(String(item.designator || "").toUpperCase()) || null,
    }))
    .sort((a, b) => a.designator.localeCompare(b.designator, "pl", { numeric: true, sensitivity: "base" }));
}

function polarityItemsForStep(project, step) {
  const designators = new Set(stepDesignatorsForPoints(step));
  return (project.polarity || []).filter((item) => (
    item.required
    && designators.has(String(item.designator || "").toUpperCase())
  ));
}

function renderOperatorPolarityNotice(items) {
  if (!items.length) {
    return "";
  }
  const configured = items.filter((item) => Number.isFinite(Number(item.plus_x)) && Number.isFinite(Number(item.plus_y)));
  const missing = items.filter((item) => !Number.isFinite(Number(item.plus_x)) || !Number.isFinite(Number(item.plus_y)));
  return `
    <div class="operator-polarity-notice">
      <strong>Uwaga: polaryzacja</strong>
      ${configured.length ? `<span>Sprawdź stronę + dla: ${escapeHtml(configured.map((item) => item.designator).join(", "))}</span>` : ""}
      ${missing.length ? `<span>Brak ustawionego + w adminie: ${escapeHtml(missing.map((item) => item.designator).join(", "))}</span>` : ""}
    </div>
  `;
}

function polarityItem(project, designator) {
  const cleanDesignator = String(designator || "").toUpperCase();
  return (project.polarity || []).find((item) => String(item.designator || "").toUpperCase() === cleanDesignator) || null;
}

function renderPolarityTab(project) {
  if (!project.board_image_path) {
    return '<div class="empty-state"><strong>Brak obrazu PCB</strong><span>Dodaj obraz, aby wskazywać polaryzację na płytce.</span></div>';
  }
  if (!project.points?.length) {
    return '<div class="empty-state"><strong>Brak punktów P&amp;P</strong><span>Zaimportuj P&amp;P, aby powiązać desygnatory z pozycjami.</span></div>';
  }

  const rows = polarityRows(project);
  const activeDesignator = rows.some((item) => item.designator === state.polarityEditDesignator)
    ? state.polarityEditDesignator
    : null;
  const required = rows.filter((item) => item.required);
  const configured = required.filter((item) => Number.isFinite(Number(item.plus_x)) && Number.isFinite(Number(item.plus_y)));
  const candidatePoints = rows.map((item) => item.point).filter(Boolean);
  const selectedDesignators = activeDesignator ? [activeDesignator] : ["__POLARITY_NONE__"];

  return `
    <div class="polarity-layout">
      <div class="polarity-board-panel">
        <div class="polarity-toolbar">
          <form data-polarity-import-form>
            <input type="file" name="fabPdf" accept=".pdf,application/pdf" required>
            <button type="submit" class="primary">Importuj Fab PDF</button>
          </form>
          <div class="polarity-stats">
            <span>Kandydaci: <strong>${rows.length}</strong></span>
            <span>Wymaga: <strong>${required.length}</strong></span>
            <span>Ustawiony plus: <strong>${configured.length}</strong></span>
          </div>
        </div>
        ${activeDesignator ? `
          <div class="polarity-active-note">
            Ustawiasz plus dla <strong>${escapeHtml(activeDesignator)}</strong>. Kliknij na zdjęciu dokładnie w miejsce oznaczenia <strong>+</strong>.
          </div>
        ` : `
          <div class="muted">Najpierw importuj Fab PDF, potem przy kondensatorach wymagających polaryzacji kliknij „Ustaw +”.</div>
        `}
        <div data-polarity-board>
          ${renderBoardMap(project, candidatePoints.length ? candidatePoints : project.points, {
            selectedDesignators,
            showSoftPoints: true,
            showLabels: true,
            markerClass: "calibration-marker",
            stageClass: "polarity-stage",
            mapClass: "polarity-map",
            polarityItems: project.polarity || [],
          })}
        </div>
      </div>
      <div class="polarity-list-panel">
        <div class="table-wrap polarity-table-wrap">
          <table class="admin-table polarity-table">
            <thead>
              <tr>
                <th>Desygnator</th>
                <th>Linia</th>
                <th>Status</th>
                <th>Akcje</th>
              </tr>
            </thead>
            <tbody>
              ${rows.length ? rows.map((item) => {
                const hasPlus = Number.isFinite(Number(item.plus_x)) && Number.isFinite(Number(item.plus_y));
                return `
                  <tr class="${item.required ? "required" : ""} ${item.designator === activeDesignator ? "active" : ""}">
                    <td>
                      <strong>${escapeHtml(item.designator)}</strong>
                      ${item.point ? "" : '<span>brak punktu P&amp;P</span>'}
                    </td>
                    <td>
                      ${item.step ? `
                        <strong>${escapeHtml(renderStepValue(item.step))}</strong>
                        <span>${escapeHtml(item.step.medcom_index || "-")}</span>
                      ` : '<span>poza liniami montażu</span>'}
                    </td>
                    <td>
                      ${item.required ? '<strong class="polarity-required">wymaga</strong>' : '<span>kandydat</span>'}
                      ${hasPlus ? '<span>plus ustawiony</span>' : '<span>brak plusa</span>'}
                    </td>
                    <td class="polarity-actions">
                      <button type="button" data-polarity-toggle="${escapeHtml(item.designator)}">${item.required ? "Wyłącz" : "Wymaga +"}</button>
                      <button type="button" class="${item.designator === activeDesignator ? "primary" : ""}" data-polarity-edit="${escapeHtml(item.designator)}">Ustaw +</button>
                      <button type="button" data-polarity-clear="${escapeHtml(item.designator)}" ${hasPlus ? "" : "disabled"}>Wyczyść</button>
                    </td>
                  </tr>
                `;
              }).join("") : '<tr><td colspan="4" class="muted">Brak kandydatów. Importuj plik Fab PDF dla tego projektu.</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;
}

async function importPolarityPdf(form) {
  if (!state.selectedProject) {
    return;
  }
  const button = form.querySelector("button");
  const previousText = button?.textContent;
  if (button) {
    button.disabled = true;
    button.textContent = "Importuję...";
  }
  try {
    const response = await apiForm(`/api/projects/${state.selectedProject.id}/polarity/import-fab-pdf`, new FormData(form));
    state.selectedProject = response.project;
    state.polarityEditDesignator = null;
    await loadProjects();
    await selectProject(response.project.id, "polarity");
    const summary = response.summary || {};
    alert(`Polaryzacja: ${summary.imported || 0} nowych, ${summary.updated || 0} odświeżonych, ${summary.autoPlus || 0} plusów z PDF, ${summary.skipped || 0} pominiętych.`);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = previousText;
    }
  }
}

async function updateComponentPolarity(designator, patch = {}) {
  if (!state.selectedProject) {
    return;
  }
  const current = polarityItem(state.selectedProject, designator) || {};
  const response = await api(`/api/projects/${state.selectedProject.id}/polarity/${encodeURIComponent(designator)}`, {
    method: "PUT",
    body: JSON.stringify({
      required: patch.required ?? Boolean(current.required),
      plusX: patch.plusX === undefined ? current.plus_x : patch.plusX,
      plusY: patch.plusY === undefined ? current.plus_y : patch.plusY,
      note: patch.note ?? current.note ?? "",
    }),
  });
  state.selectedProject = response.project;
  await loadProjects();
  renderProjectDetails();
}

function attachPolarityTools() {
  if (!state.selectedProject || state.activeProjectTab !== "polarity") {
    return;
  }
  els.projectDetails.querySelector("[data-polarity-import-form]")?.addEventListener("submit", (event) => {
    event.preventDefault();
    importPolarityPdf(event.currentTarget).catch((error) => alert(error.message));
  });
  els.projectDetails.querySelectorAll("[data-polarity-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = polarityItem(state.selectedProject, button.dataset.polarityToggle);
      updateComponentPolarity(button.dataset.polarityToggle, { required: !item?.required }).catch((error) => alert(error.message));
    });
  });
  els.projectDetails.querySelectorAll("[data-polarity-edit]").forEach((button) => {
    button.addEventListener("click", () => {
      state.polarityEditDesignator = button.dataset.polarityEdit;
      renderProjectDetails();
    });
  });
  els.projectDetails.querySelectorAll("[data-polarity-clear]").forEach((button) => {
    button.addEventListener("click", () => {
      updateComponentPolarity(button.dataset.polarityClear, { plusX: null, plusY: null }).catch((error) => alert(error.message));
    });
  });
  const source = els.projectDetails.querySelector("[data-polarity-board] .operator-board-source");
  if (source) {
    source.addEventListener("click", (event) => {
      if (!state.polarityEditDesignator) {
        return;
      }
      const coords = boardCoordinatesFromSourceClick(event, state.selectedProject);
      updateComponentPolarity(state.polarityEditDesignator, {
        required: true,
        plusX: Number(coords.x.toFixed(3)),
        plusY: Number(coords.y.toFixed(3)),
      }).catch((error) => alert(error.message));
    });
  }
}

async function updateFeedbackStatus(form) {
  if (!state.selectedProject) {
    return;
  }
  const data = formData(form);
  const response = await api(`/api/projects/${state.selectedProject.id}/feedback/${form.dataset.feedbackForm}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
  state.selectedProject = response.project;
  await loadProjects();
  await selectProject(response.project.id, "operator");
}

function renderOperatorFeedbackTab(project) {
  const feedback = project.operator_feedback || [];
  const openFeedback = feedback.filter((item) => ["open", "in_progress"].includes(item.admin_status));
  const statusOptions = [
    ["open", "Otwarte"],
    ["in_progress", "W trakcie"],
    ["fixed", "Poprawione"],
    ["verified", "Zweryfikowane"],
    ["rejected", "Odrzucone"],
  ];
  return `
    <div class="summary-grid">
      <div class="summary-box">
        <strong>Zakres operatora</strong>
        <span>Liczba kroków: ${project.steps?.length || 0}</span>
        <span>Liczba punktów: ${project.points?.length || 0}</span>
        <span>Status projektu: ${escapeHtml(statusLabel(project.status))}</span>
      </div>
      <div class="summary-box">
        <strong>Zgłoszenia</strong>
        <span>Otwarte / w trakcie: ${openFeedback.length}</span>
        <span>Historia zgłoszeń: ${feedback.length}</span>
      </div>
    </div>
    <div class="operator-feedback-admin">
      <h3>Uwagi operatora</h3>
      ${feedback.length ? feedback.map((item) => `
        <form class="feedback-item ${escapeHtml(item.admin_status)}" data-feedback-form="${item.id}">
          <div>
            <strong>${escapeHtml(operatorFeedbackTypeLabel(item.feedback_type))}: ${escapeHtml(item.value || "-")}</strong>
            <span>Krok ${escapeHtml(item.step_no)} | ${escapeHtml(item.designators || "-")} | ${escapeHtml(item.medcom_index || "-")}</span>
            ${item.note ? `<p>${escapeHtml(item.note)}</p>` : '<p class="muted">Brak dopisanej uwagi operatora.</p>'}
            <em>${escapeHtml(formatDate(item.created_at))}</em>
            <button type="button" data-open-feedback-step="${item.step_id}">Otwórz linię PRO</button>
          </div>
          <label>
            Status admina
            <select name="adminStatus">
              ${statusOptions.map(([value, label]) => `<option value="${value}" ${item.admin_status === value ? "selected" : ""}>${label}</option>`).join("")}
            </select>
          </label>
          <label>
            Notatka admina
            <textarea name="adminNote" rows="2" placeholder="Co poprawiono / decyzja">${escapeHtml(item.admin_note || "")}</textarea>
          </label>
          <button type="submit">Zapisz status</button>
        </form>
      `).join("") : '<div class="empty-state"><strong>Brak zgłoszeń</strong><span>Problemy i pominięcia z panelu operatora pojawią się tutaj.</span></div>'}
    </div>
  `;
}

function operatorFeedbackTypeLabel(type) {
  const labels = {
    problem: "Problem",
    skipped: "Pominięto",
    note: "Uwaga",
  };
  return labels[type] || type || "Uwaga";
}

function renderOperatorTab(project) {
  return `
    <div class="summary-grid">
      <div class="summary-box">
        <strong>Zakres dla operatora</strong>
        <span>Liczba kroków: ${project.steps?.length || 0}</span>
        <span>Liczba punktów: ${project.points?.length || 0}</span>
        <span>Status projektu: ${escapeHtml(statusLabel(project.status))}</span>
      </div>
      <div class="summary-box">
        <strong>Sesje</strong>
        <span>Uwagi operatora zapisują się w sesjach.</span>
        <span>Aktualna sesja: ${state.currentSession ? "aktywna" : "brak"}</span>
      </div>
    </div>
  `;
}

function operatorStepsForProject(project) {
  return (project?.steps || []).filter((step) => !stepIsSkipped(step));
}

function operatorStepStatus(step) {
  return latestEventForStep(step.id)?.status || "pending";
}

function operatorStatusLabel(status) {
  const labels = {
    pending: "Do zrobienia",
    done: "OK",
    problem: "Problem",
    skipped: "Pominięty",
  };
  return labels[status] || status;
}

function isOperatorStepHandled(step) {
  return ["done", "problem", "skipped"].includes(operatorStepStatus(step));
}

function stepDesignatorsForPoints(step) {
  const segments = stepSegments(step);
  if (segments.length) {
    return Array.from(new Set(segments.flatMap((segment) => segment.designators || [])));
  }
  return splitDesignators(step.designators);
}

function pointsForStep(project, step) {
  const designators = new Set(stepDesignatorsForPoints(step));
  return (project.points || []).filter((point) => designators.has(String(point.designator || "").toUpperCase()));
}

function normalizeBoardCalibration(calibration = {}) {
  const rotation = [0, 90, 180, 270].includes(Number(calibration.rotation)) ? Number(calibration.rotation) : 0;
  const numberValue = (value, fallback) => {
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  };
  const offsetX = Math.max(-50, Math.min(50, numberValue(calibration.offsetX, 0)));
  const offsetY = Math.max(-50, Math.min(50, numberValue(calibration.offsetY, 0)));
  const scaleX = Math.max(0.2, Math.min(3, numberValue(calibration.scaleX, 1)));
  const scaleY = Math.max(0.2, Math.min(3, numberValue(calibration.scaleY, 1)));
  return {
    rotation,
    flipX: Boolean(calibration.flipX),
    flipY: Boolean(calibration.flipY),
    offsetX,
    offsetY,
    scaleX,
    scaleY,
  };
}

function storedBoardCalibration(project) {
  return normalizeBoardCalibration(project?.board_calibration || {});
}

function activeBoardCalibration(project) {
  return normalizeBoardCalibration(state.calibrationDrafts.get(project.id) || storedBoardCalibration(project));
}

function boardBaseMetrics(project, points) {
  const projectWidth = Number(project.board_width) || 0;
  const projectHeight = Number(project.board_height) || 0;
  const metricPoints = project.points?.length ? project.points : (points || []);
  const pointCoordinates = metricPoints
    .map((point) => ({
      x: Number(point.x),
      y: Number(point.y),
    }))
    .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));

  const profile = project?.board_contours?.profile || {};
  const profileWidth = Number(profile.width);
  const profileHeight = Number(profile.height);
  const profileOriginX = Number(profile.x);
  const profileOriginY = Number(profile.y);
  if (
    profile.fromProfile
    && Number.isFinite(profileWidth)
    && Number.isFinite(profileHeight)
    && profileWidth > 0
    && profileHeight > 0
  ) {
    let rawFit = 0;
    let localFit = 0;
    pointCoordinates.forEach((point) => {
      if (
        Number.isFinite(profileOriginX)
        && Number.isFinite(profileOriginY)
        && point.x >= profileOriginX - 2
        && point.x <= profileOriginX + profileWidth + 2
        && point.y >= profileOriginY - 2
        && point.y <= profileOriginY + profileHeight + 2
      ) {
        rawFit += 1;
      }
      if (point.x >= -2 && point.x <= profileWidth + 2 && point.y >= -2 && point.y <= profileHeight + 2) {
        localFit += 1;
      }
    });
    return {
      width: profileWidth,
      height: profileHeight,
      originX: rawFit > localFit && Number.isFinite(profileOriginX) ? profileOriginX : 0,
      originY: rawFit > localFit && Number.isFinite(profileOriginY) ? profileOriginY : 0,
      swapped: false,
    };
  }

  if (!projectWidth || !projectHeight) {
    const maxX = Math.max(0, ...pointCoordinates.map((point) => point.x));
    const maxY = Math.max(0, ...pointCoordinates.map((point) => point.y));
    return {
      width: maxX || 1,
      height: maxY || 1,
      originX: 0,
      originY: 0,
      swapped: false,
    };
  }

  const rawMaxX = pointCoordinates.length ? Math.max(...pointCoordinates.map((point) => point.x)) : 0;
  const rawMaxY = pointCoordinates.length ? Math.max(...pointCoordinates.map((point) => point.y)) : 0;
  const rawMinX = pointCoordinates.length ? Math.min(...pointCoordinates.map((point) => point.x)) : 0;
  const rawMinY = pointCoordinates.length ? Math.min(...pointCoordinates.map((point) => point.y)) : 0;
  const maxX = Math.max(0, rawMaxX);
  const maxY = Math.max(0, rawMaxY);
  const looksSwapped = Boolean(
    pointCoordinates.length
    && maxY > projectHeight
    && maxY <= projectWidth * 1.03
    && maxX <= projectHeight * 1.03
  );

  const width = looksSwapped ? projectHeight : projectWidth;
  const height = looksSwapped ? projectWidth : projectHeight;
  const toleranceX = Math.max(1, width * 0.03);
  const toleranceY = Math.max(1, height * 0.03);
  const originX = rawMaxX > width + toleranceX
    ? rawMaxX - width
    : rawMinX < -toleranceX
      ? rawMinX
      : 0;
  const originY = rawMaxY <= 0 && rawMinY < -toleranceY
    ? rawMaxY - height
    : rawMaxY > height + toleranceY
      ? rawMaxY - height
      : rawMinY < -toleranceY
        ? rawMinY
        : 0;

  return {
    width,
    height,
    originX,
    originY,
    swapped: looksSwapped,
  };
}

function boardMapMetrics(project, points, calibration = storedBoardCalibration(project)) {
  const base = boardBaseMetrics(project, points);
  const cleanCalibration = normalizeBoardCalibration(calibration);
  const sideways = cleanCalibration.rotation === 90 || cleanCalibration.rotation === 270;
  return {
    ...base,
    calibration: cleanCalibration,
    displayWidth: sideways ? base.height : base.width,
    displayHeight: sideways ? base.width : base.height,
  };
}

function boardMapStyle(metrics, options = {}) {
  const displayWidth = Number(metrics.displayWidth) || 1;
  const displayHeight = Number(metrics.displayHeight) || 1;
  const ratio = displayWidth / displayHeight;
  const zoom = Number(options.zoomPercent) || 0;
  const zoomStyle = zoom
    ? `width: ${Math.max(35, Math.min(240, zoom))}%; max-width: none;`
    : `--board-max-width: ${ratio * 72}vh;`;
  return `--board-ratio: ${ratio}; ${zoomStyle} aspect-ratio: ${displayWidth} / ${displayHeight};`;
}

function applyBoardCalibrationToNormalizedPoint(point, calibration) {
  let x = point.x;
  let y = point.y;

  if (calibration.rotation === 90) {
    [x, y] = [1 - y, x];
  } else if (calibration.rotation === 180) {
    [x, y] = [1 - x, 1 - y];
  } else if (calibration.rotation === 270) {
    [x, y] = [y, 1 - x];
  }

  if (calibration.flipX) {
    x = 1 - x;
  }
  if (calibration.flipY) {
    y = 1 - y;
  }

  x = 0.5 + (x - 0.5) * (Number(calibration.scaleX) || 1) + (Number(calibration.offsetX) || 0) / 100;
  y = 0.5 + (y - 0.5) * (Number(calibration.scaleY) || 1) + (Number(calibration.offsetY) || 0) / 100;

  return {
    x: Math.max(0, Math.min(1, x)),
    y: Math.max(0, Math.min(1, y)),
  };
}

function invertBoardCalibrationFromNormalizedPoint(point, calibration) {
  let x = Math.max(0, Math.min(1, Number(point.x) || 0));
  let y = Math.max(0, Math.min(1, Number(point.y) || 0));
  const cleanCalibration = normalizeBoardCalibration(calibration);

  x = ((x - cleanCalibration.offsetX / 100) - 0.5) / cleanCalibration.scaleX + 0.5;
  y = ((y - cleanCalibration.offsetY / 100) - 0.5) / cleanCalibration.scaleY + 0.5;

  if (cleanCalibration.flipX) {
    x = 1 - x;
  }
  if (cleanCalibration.flipY) {
    y = 1 - y;
  }

  if (cleanCalibration.rotation === 90) {
    [x, y] = [y, 1 - x];
  } else if (cleanCalibration.rotation === 180) {
    [x, y] = [1 - x, 1 - y];
  } else if (cleanCalibration.rotation === 270) {
    [x, y] = [1 - y, x];
  }

  return {
    x: Math.max(0, Math.min(1, x)),
    y: Math.max(0, Math.min(1, y)),
  };
}

function boardCoordinatesFromSourceClick(event, project) {
  const source = event.currentTarget;
  const rect = source.getBoundingClientRect();
  const x = (event.clientX - rect.left) / Math.max(1, rect.width);
  const y = (event.clientY - rect.top) / Math.max(1, rect.height);
  const metrics = boardMapMetrics(project, project.points || []);
  const base = invertBoardCalibrationFromNormalizedPoint({ x, y }, metrics.calibration || {});
  return {
    x: Number(metrics.originX || 0) + Math.max(0, Math.min(metrics.width, base.x * metrics.width)),
    y: Number(metrics.originY || 0) + Math.max(0, Math.min(metrics.height, metrics.height - base.y * metrics.height)),
  };
}

function boardPointPosition(point, metrics) {
  const boardWidth = Number(metrics.width) || 1;
  const boardHeight = Number(metrics.height) || 1;
  const originX = Number(metrics.originX) || 0;
  const originY = Number(metrics.originY) || 0;
  const base = {
    x: Math.max(0, Math.min(1, (Number(point.x) - originX) / boardWidth)),
    y: Math.max(0, Math.min(1, (boardHeight - (Number(point.y) - originY)) / boardHeight)),
  };
  const calibrated = applyBoardCalibrationToNormalizedPoint(base, metrics.calibration || {});
  return {
    x: calibrated.x * 100,
    y: calibrated.y * 100,
  };
}

function boardLocalPointPosition(point, metrics) {
  const boardWidth = Number(metrics.width) || 1;
  const boardHeight = Number(metrics.height) || 1;
  const base = {
    x: Math.max(0, Math.min(1, Number(point.x) / boardWidth)),
    y: Math.max(0, Math.min(1, (boardHeight - Number(point.y)) / boardHeight)),
  };
  const calibrated = applyBoardCalibrationToNormalizedPoint(base, metrics.calibration || {});
  return {
    x: calibrated.x * 100,
    y: calibrated.y * 100,
  };
}

function boardContourStyle(contour, metrics) {
  const x = Number(contour.x) || 0;
  const y = Number(contour.y) || 0;
  const width = Math.max(0.1, Number(contour.width) || 0);
  const height = Math.max(0.1, Number(contour.height) || 0);
  const topLeft = boardLocalPointPosition({ x, y: y + height }, metrics);
  const bottomRight = boardLocalPointPosition({ x: x + width, y }, metrics);
  const left = Math.min(topLeft.x, bottomRight.x);
  const right = Math.max(topLeft.x, bottomRight.x);
  const top = Math.min(topLeft.y, bottomRight.y);
  const bottom = Math.max(topLeft.y, bottomRight.y);
  return [
    `left: ${left}%`,
    `top: ${top}%`,
    `width: ${Math.max(0.2, right - left)}%`,
    `height: ${Math.max(0.2, bottom - top)}%`,
  ].join("; ");
}

function setCalibrationDraft(project, patch) {
  const next = normalizeBoardCalibration({
    ...activeBoardCalibration(project),
    ...patch,
  });
  state.calibrationDrafts.set(project.id, next);
  renderProjectDetails();
}

function calibrationDesignators(project) {
  const stored = state.calibrationDesignators.get(project.id);
  if (stored !== undefined) {
    return stored;
  }
  const points = project.points || [];
  if (!points.length) {
    return "";
  }
  const selected = [];
  const addPoint = (point) => {
    const designator = String(point?.designator || "").trim().toUpperCase();
    if (designator && !selected.includes(designator)) {
      selected.push(designator);
    }
  };
  addPoint(points.reduce((best, point) => (Number(point.x) < Number(best.x) ? point : best), points[0]));
  addPoint(points.reduce((best, point) => (Number(point.x) > Number(best.x) ? point : best), points[0]));
  addPoint(points.reduce((best, point) => (Number(point.y) < Number(best.y) ? point : best), points[0]));
  addPoint(points.reduce((best, point) => (Number(point.y) > Number(best.y) ? point : best), points[0]));
  addPoint(points[Math.floor(points.length / 2)]);
  return selected.join(",");
}

function renderBoardMap(project, points, options = {}) {
  if (!project.board_image_path) {
    return '<div class="operator-board-empty">Brak obrazu PCB</div>';
  }
  const calibration = options.calibration || storedBoardCalibration(project);
  const sourceMetrics = boardMapMetrics(project, project.points || points, calibration);
  const viewRotation = normalizeViewRotation(options.viewRotation);
  const viewSideways = viewRotation === 90 || viewRotation === 270;
  const metrics = {
    ...sourceMetrics,
    displayWidth: viewSideways ? sourceMetrics.displayHeight : sourceMetrics.displayWidth,
    displayHeight: viewSideways ? sourceMetrics.displayWidth : sourceMetrics.displayHeight,
  };
  const sourceRatio = (Number(sourceMetrics.displayWidth) || 1) / (Number(sourceMetrics.displayHeight) || 1);
  const selectedDesignators = new Set((options.selectedDesignators || []).map((item) => String(item).toUpperCase()));
  const showSoftPoints = Boolean(options.showSoftPoints);
  const showLabels = options.showLabels !== false;
  const markerClass = options.markerClass || "operator-board-marker";
  const paletteClass = `marker-${normalizeMarkerPalette(options.markerPalette)}`;
  const operatorMarkerSize = markerClass === "operator-board-marker"
    ? operatorMarkerSizeForZoom(Number(options.zoomPercent) || 100, options.markerSizePercent)
    : null;
  const markers = sourceMetrics.width > 0 && sourceMetrics.height > 0
    ? (points || []).map((point) => {
      const position = boardPointPosition(point, sourceMetrics);
      const designator = String(point.designator || "").toUpperCase();
      const isSelected = selectedDesignators.size === 0 || selectedDesignators.has(designator);
      if (!isSelected && !showSoftPoints) {
        return "";
      }
      const classes = [
        markerClass,
        isSelected ? "active" : "soft",
      ].join(" ");
      const label = isSelected && showLabels ? `<span>${escapeHtml(point.designator)}</span>` : "";
      return `
        <span class="${classes}" data-board-marker="${isSelected ? "active" : "soft"}" style="left: ${position.x}%; top: ${position.y}%;">
          ${label}
        </span>
      `;
    }).join("")
    : "";
  const polarityMarkers = sourceMetrics.width > 0 && sourceMetrics.height > 0
    ? (options.polarityItems || []).map((item) => {
      const plusX = Number(item.plus_x);
      const plusY = Number(item.plus_y);
      if (!item.required || !Number.isFinite(plusX) || !Number.isFinite(plusY)) {
        return "";
      }
      const position = boardPointPosition({ x: plusX, y: plusY }, sourceMetrics);
      const designator = String(item.designator || "").toUpperCase();
      const selected = selectedDesignators.size === 0 || selectedDesignators.has(designator);
      return `
        <span class="polarity-plus-marker ${selected ? "active" : ""}" style="left: ${position.x}%; top: ${position.y}%;">
          <b>+</b>
          ${showLabels ? `<em>${escapeHtml(designator)}</em>` : ""}
        </span>
      `;
    }).join("")
    : "";
  const contourItems = Array.isArray(options.contours) ? options.contours : [];
  const contourMarkers = sourceMetrics.width > 0 && sourceMetrics.height > 0
    ? contourItems.map((contour) => {
      const isSelected = contourMatchesDesignators(contour, selectedDesignators);
      if (!isSelected && !options.showSoftContours) {
        return "";
      }
      const style = boardContourStyle(contour, sourceMetrics);
      const label = isSelected && showLabels && contourDesignators(contour).length
        ? `<span>${escapeHtml(contourDesignators(contour).slice(0, 3).join(","))}</span>`
        : "";
      const inferredClass = contour.inferred ? " inferred" : "";
      return `
        <span class="operator-board-contour ${isSelected ? "active" : "soft"}${inferredClass}" style="${style}" data-board-contour="${escapeHtml(contour.id || "")}">
          ${label}
        </span>
      `;
    }).join("")
    : "";
  const stageAttribute = options.operatorStage ? ' data-operator-board-stage' : "";
  const stageStyle = operatorMarkerSize ? ` style="--operator-marker-size: ${operatorMarkerSize}px;"` : "";

  return `
    <div class="operator-board-stage ${paletteClass} ${options.stageClass || ""}"${stageAttribute}${stageStyle}>
      <div class="operator-board-map ${options.mapClass || ""}" style="${boardMapStyle(metrics, { zoomPercent: options.zoomPercent })} --source-ratio: ${sourceRatio};">
        <div class="operator-board-source rotate-${viewRotation}">
          <img src="${escapeHtml(boardImageUrl(project.board_image_path, project.updated_at))}" alt="Obraz PCB">
          ${contourMarkers}
          ${markers}
          ${polarityMarkers}
        </div>
      </div>
    </div>
  `;
}

function resolveOperatorStep(steps) {
  if (!steps.length) {
    state.operatorActiveStepId = null;
    return null;
  }
  const active = steps.find((step) => Number(step.id) === Number(state.operatorActiveStepId));
  if (active) {
    return active;
  }
  const firstOpen = steps.find((step) => !isOperatorStepHandled(step)) || steps[0];
  state.operatorActiveStepId = firstOpen.id;
  return firstOpen;
}

function operatorProgress(steps) {
  const handled = steps.filter(isOperatorStepHandled).length;
  const problems = steps.filter((step) => operatorStepStatus(step) === "problem").length;
  const done = steps.filter((step) => operatorStepStatus(step) === "done").length;
  return {
    handled,
    done,
    problems,
    total: steps.length,
    percent: steps.length ? Math.round((handled / steps.length) * 100) : 0,
  };
}

function renderOperatorCommandBar(project, currentStep, progress) {
  const view = state.operatorView;
  const previewImages = projectPreviewImages(project);
  const markerOptions = [
    ["contrast", "Kontrast"],
    ["magenta", "Różowy"],
    ["cyan", "Cyjan"],
    ["amber", "Żółty"],
  ];
  return `
    <div class="operator-commandbar">
      <div class="operator-session-strip">
        <button type="button" data-operator-back>Projekty</button>
        <strong>${escapeHtml(project.name)}</strong>
        <div class="operator-progress-mini">
          <span>${progress.handled} / ${progress.total} (${progress.percent}%) | OK: ${progress.done} | Problem: ${progress.problems}</span>
          <div><i style="width: ${progress.percent}%"></i></div>
        </div>
      </div>
      <div class="operator-view-controls">
        <label class="operator-zoom-control">
          <span>Rozmiar</span>
          <input type="range" min="35" max="240" step="5" value="${view.zoom}" data-operator-zoom>
          <strong data-operator-zoom-label>${view.zoom}%</strong>
        </label>
        <label class="operator-marker-size-control">
          <span>Punkt</span>
          <input type="range" min="75" max="180" step="5" value="${view.markerSize}" data-operator-marker-size>
          <strong data-operator-marker-size-label>${view.markerSize}%</strong>
        </label>
        <div class="operator-segment">
          <span>Obrót</span>
          ${[0, 90, 180, 270].map((rotation) => `
            <button type="button" class="${view.rotation === rotation ? "active" : ""}" data-operator-rotation="${rotation}">${rotation}</button>
          `).join("")}
        </div>
        <div class="operator-segment marker-segment">
          <span>Marker</span>
          ${markerOptions.map(([value, label]) => `
            <button type="button" class="marker-choice marker-${value} ${view.markerPalette === value ? "active" : ""}" title="${label}" data-operator-marker="${value}">
              <i></i>
            </button>
          `).join("")}
        </div>
        <button type="button" class="${view.focusMode ? "active" : ""}" data-operator-focus>Focus</button>
        <button type="button" class="${view.showLabels ? "active" : ""}" data-operator-toggle-labels>Opisy: ${view.showLabels ? "ON" : "OFF"}</button>
        <button type="button" class="${view.showPolarity ? "active" : ""}" data-operator-toggle-polarity>Polaryzacja: ${view.showPolarity ? "ON" : "OFF"}</button>
        <button type="button" class="${view.showContours ? "active" : ""}" data-operator-toggle-contours>Kontur: ${view.showContours ? "ON" : "OFF"}</button>
        ${previewImages.map((image) => `
          <button type="button" data-operator-preview-image="${image.key}">${escapeHtml(image.label)}</button>
        `).join("")}
        <button type="button" data-operator-fullscreen>Full screen</button>
      </div>
    </div>
  `;
}

function renderOperatorBoard(project, step) {
  if (!project.board_image_path) {
    return '<div class="operator-board-empty">Brak obrazu PCB</div>';
  }
  const activePoints = pointsForStep(project, step);
  const visiblePoints = state.operatorView.showAllPoints ? (project.points || []) : activePoints;
  const board = boardMapMetrics(project, project.points || activePoints);
  const calibration = storedBoardCalibration(project);
  const activeDesignators = activePoints.map((point) => String(point.designator || "").toUpperCase());
  const missing = stepDesignatorsForPoints(step).filter((designator) => !activePoints.some((point) => String(point.designator || "").toUpperCase() === designator));
  const polarityItems = state.operatorView.showPolarity ? polarityItemsForStep(project, step) : [];
  const stepContours = state.operatorView.showContours ? contoursForStep(project, step) : [];

  return `
    <div class="operator-board-shell">
      ${renderBoardMap(project, visiblePoints, {
        selectedDesignators: activeDesignators.length ? activeDesignators : ["__NO_ACTIVE_POINT__"],
        showSoftPoints: state.operatorView.showAllPoints,
        showLabels: state.operatorView.showLabels,
        markerClass: "operator-board-marker",
        markerPalette: state.operatorView.markerPalette,
        markerSizePercent: state.operatorView.markerSize,
        viewRotation: state.operatorView.rotation,
        zoomPercent: state.operatorView.zoom,
        operatorStage: true,
        polarityItems,
        contours: stepContours,
      })}
      <div class="operator-board-meta">
        <span>${activePoints.length ? `Punkty: ${activePoints.map((point) => point.designator).join(", ")}` : "Brak punktu P&P dla tej linii"}</span>
        ${board.swapped ? '<span>Wykryto zamienione wymiary PCB: podgląd używa osi P&amp;P.</span>' : ""}
        ${calibration.rotation || calibration.flipX || calibration.flipY ? '<span>Kalibracja PCB aktywna.</span>' : ""}
        ${missing.length ? `<span>Bez punktu: ${escapeHtml(missing.join(", "))}</span>` : ""}
      </div>
    </div>
  `;
}

function renderOperatorPreviewModal(project) {
  const selected = projectPreviewImage(project, state.operatorPreviewImage);
  if (!selected) {
    return "";
  }
  const images = projectPreviewImages(project);
  return `
    <div class="operator-preview-modal" data-operator-preview-modal>
      <div class="operator-preview-dialog">
        <div class="operator-preview-head">
          <div>
            <strong>${escapeHtml(selected.label)}</strong>
            <span>${escapeHtml(project.name)}</span>
          </div>
          <div class="operator-preview-actions">
            ${images.map((image) => `
              <button type="button" class="${image.key === selected.key ? "active" : ""}" data-operator-preview-image="${image.key}">
                ${escapeHtml(image.label)}
              </button>
            `).join("")}
            <button type="button" data-close-operator-preview>Zamknij</button>
          </div>
        </div>
        <div class="operator-preview-image">
          <img src="${escapeHtml(boardImageUrl(selected.path, project.updated_at))}" alt="${escapeHtml(selected.label)}">
        </div>
      </div>
    </div>
  `;
}

function renderOperatorStepList(steps, currentStep) {
  return `
    <div class="operator-step-rail">
      <table class="operator-step-table">
        <thead>
          <tr>
            <th></th>
            <th>Lp.</th>
            <th>Desygnatory</th>
            <th>Ilość</th>
            <th>Wartość</th>
          </tr>
        </thead>
        <tbody>
        ${steps.map((step) => {
        const status = operatorStepStatus(step);
        const active = Number(step.id) === Number(currentStep.id) ? " active" : "";
        return `
          <tr class="${status}${active}" data-operator-jump-step="${step.id}">
            <td><span class="status-dot"></span></td>
            <td>${step.step_no}</td>
            <td>${escapeHtml(stepDesignatorsForPoints(step).join(", "))}</td>
            <td>${escapeHtml(renderStepQuantity(step))}</td>
            <td>${escapeHtml(renderStepValue(step))}</td>
          </tr>
        `;
      }).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function operatorActiveMarkers() {
  return Array.from(els.operatorSteps.querySelectorAll('[data-board-marker="active"], .polarity-plus-marker.active'));
}

function operatorMarkerBounds(markers) {
  return markers.reduce((box, marker) => {
    const rect = marker.getBoundingClientRect();
    return {
      left: Math.min(box.left, rect.left),
      top: Math.min(box.top, rect.top),
      right: Math.max(box.right, rect.right),
      bottom: Math.max(box.bottom, rect.bottom),
    };
  }, {
    left: Number.POSITIVE_INFINITY,
    top: Number.POSITIVE_INFINITY,
    right: Number.NEGATIVE_INFINITY,
    bottom: Number.NEGATIVE_INFINITY,
  });
}

function operatorStageMarkerBounds(stage, markers) {
  const stageRect = stage.getBoundingClientRect();
  return markers.reduce((box, marker) => {
    const rect = marker.getBoundingClientRect();
    return {
      left: Math.min(box.left, rect.left - stageRect.left + stage.scrollLeft),
      top: Math.min(box.top, rect.top - stageRect.top + stage.scrollTop),
      right: Math.max(box.right, rect.right - stageRect.left + stage.scrollLeft),
      bottom: Math.max(box.bottom, rect.bottom - stageRect.top + stage.scrollTop),
    };
  }, {
    left: Number.POSITIVE_INFINITY,
    top: Number.POSITIVE_INFINITY,
    right: Number.NEGATIVE_INFINITY,
    bottom: Number.NEGATIVE_INFINITY,
  });
}

function clampScroll(value, maxValue) {
  return Math.max(0, Math.min(Math.max(0, maxValue), value));
}

function operatorLabelOverlap(a, b, padding = 5) {
  const left = Math.max(a.x - padding, b.x - padding);
  const right = Math.min(a.x + a.width + padding, b.x + b.width + padding);
  const top = Math.max(a.y - padding, b.y - padding);
  const bottom = Math.min(a.y + a.height + padding, b.y + b.height + padding);
  return right <= left || bottom <= top ? 0 : (right - left) * (bottom - top);
}

function placeOperatorLabels() {
  const stage = els.operatorSteps.querySelector("[data-operator-board-stage]");
  const source = stage?.querySelector(".operator-board-source");
  const markers = operatorActiveMarkers();
  if (!stage || !source || !markers.length) {
    return;
  }
  const sourceRect = source.getBoundingClientRect();
  const placed = [];

  markers.forEach((marker, index) => {
    const label = marker.querySelector("span");
    if (!label) {
      return;
    }
    label.style.setProperty("--label-offset-x", "11px");
    label.style.setProperty("--label-offset-y", "-22px");

    const markerRect = marker.getBoundingClientRect();
    const markerX = markerRect.left + markerRect.width / 2 - sourceRect.left;
    const markerY = markerRect.top + markerRect.height / 2 - sourceRect.top;
    const labelWidth = Math.max(34, label.offsetWidth || 34);
    const labelHeight = Math.max(16, label.offsetHeight || 16);
    const baseGap = 11;
    const candidates = [
      { x: markerX + baseGap, y: markerY - labelHeight - 5 },
      { x: markerX + baseGap, y: markerY + 5 },
      { x: markerX - labelWidth - baseGap, y: markerY - labelHeight - 5 },
      { x: markerX - labelWidth - baseGap, y: markerY + 5 },
      { x: markerX - labelWidth / 2, y: markerY - labelHeight - 14 },
      { x: markerX - labelWidth / 2, y: markerY + 14 },
      { x: markerX + 18, y: markerY - labelHeight / 2 },
      { x: markerX - labelWidth - 18, y: markerY - labelHeight / 2 },
    ];
    const verticalStep = labelHeight + 3;
    for (let ring = 1; ring <= 3; ring += 1) {
      candidates.push({ x: markerX + baseGap, y: markerY - labelHeight - 5 - verticalStep * ring });
      candidates.push({ x: markerX + baseGap, y: markerY + 5 + verticalStep * ring });
      candidates.push({ x: markerX - labelWidth - baseGap, y: markerY - labelHeight - 5 - verticalStep * ring });
      candidates.push({ x: markerX - labelWidth - baseGap, y: markerY + 5 + verticalStep * ring });
    }

    const ordered = candidates.slice(index % candidates.length).concat(candidates.slice(0, index % candidates.length));
    let best = null;
    let bestScore = Number.POSITIVE_INFINITY;
    ordered.forEach((candidate) => {
      const rect = {
        x: Math.max(8, Math.min(Math.max(8, sourceRect.width - labelWidth - 8), candidate.x)),
        y: Math.max(8, Math.min(Math.max(8, sourceRect.height - labelHeight - 8), candidate.y)),
        width: labelWidth,
        height: labelHeight,
      };
      const overlapScore = placed.reduce((total, placedRect) => total + operatorLabelOverlap(rect, placedRect), 0);
      const distanceScore = Math.abs(rect.x + labelWidth / 2 - markerX) + Math.abs(rect.y + labelHeight / 2 - markerY);
      const score = overlapScore * 10000 + distanceScore;
      if (score < bestScore) {
        best = rect;
        bestScore = score;
      }
    });
    if (best) {
      placed.push(best);
      label.style.setProperty("--label-offset-x", `${Math.round(best.x - markerX)}px`);
      label.style.setProperty("--label-offset-y", `${Math.round(best.y - markerY)}px`);
    }
  });
}

function setOperatorBoardZoom(zoom, baseZoom = null) {
  const stage = els.operatorSteps.querySelector("[data-operator-board-stage]");
  const map = stage?.querySelector(".operator-board-map");
  const safeZoom = Math.round(Math.max(OPERATOR_AUTO_FIT_MIN_ZOOM, Math.min(240, Number(zoom) || 100)));
  if (map) {
    map.style.width = `${safeZoom}%`;
    map.style.maxWidth = "none";
  }
  if (stage) {
    stage.style.setProperty("--operator-marker-size", `${operatorMarkerSizeForZoom(safeZoom, state.operatorView.markerSize)}px`);
  }
  const zoomLabel = els.operatorSteps.querySelector("[data-operator-zoom-label]");
  if (zoomLabel) {
    zoomLabel.textContent = baseZoom && safeZoom < baseZoom
      ? `${baseZoom}% -> auto ${safeZoom}%`
      : `${safeZoom}%`;
  }
  return safeZoom;
}

function setOperatorMarkerSize(value) {
  state.operatorView.markerSize = clampMarkerSize(value);
  saveOperatorViewState();
  const input = els.operatorSteps.querySelector("[data-operator-marker-size]");
  const label = els.operatorSteps.querySelector("[data-operator-marker-size-label]");
  const stage = els.operatorSteps.querySelector("[data-operator-board-stage]");
  const map = stage?.querySelector(".operator-board-map");
  const effectiveZoom = map ? Number.parseFloat(map.style.width) || state.operatorView.zoom : state.operatorView.zoom;
  if (input) {
    input.value = String(state.operatorView.markerSize);
  }
  if (label) {
    label.textContent = `${state.operatorView.markerSize}%`;
  }
  if (stage) {
    stage.style.setProperty("--operator-marker-size", `${operatorMarkerSizeForZoom(effectiveZoom, state.operatorView.markerSize)}px`);
  }
  placeOperatorLabels();
}

function applyOperatorAutoFit() {
  const stage = els.operatorSteps.querySelector("[data-operator-board-stage]");
  if (!stage) {
    return;
  }
  const baseZoom = clampOperatorZoom(state.operatorView.zoom);
  setOperatorBoardZoom(baseZoom);
  const activeMarkers = operatorActiveMarkers();
  if (activeMarkers.length <= 1) {
    placeOperatorLabels();
    centerOperatorBoardOnCurrent();
    return;
  }

  const stageRect = stage.getBoundingClientRect();
  if (!stageRect.width || !stageRect.height) {
    return;
  }
  const bounds = operatorMarkerBounds(activeMarkers);
  const marginX = Math.min(150, Math.max(54, stage.clientWidth * 0.16));
  const marginY = Math.min(130, Math.max(54, stage.clientHeight * 0.14));
  const availableWidth = Math.max(1, stage.clientWidth - marginX * 2);
  const availableHeight = Math.max(1, stage.clientHeight - marginY * 2);
  const fitScale = Math.min(
    1,
    availableWidth / Math.max(1, bounds.right - bounds.left),
    availableHeight / Math.max(1, bounds.bottom - bounds.top),
  );
  const fitZoom = Math.round(Math.max(OPERATOR_AUTO_FIT_MIN_ZOOM, Math.min(baseZoom, baseZoom * fitScale)));
  if (fitZoom < baseZoom) {
    setOperatorBoardZoom(fitZoom, baseZoom);
  }
  placeOperatorLabels();
  centerOperatorBoardOnCurrent();
}

function scheduleOperatorAutoFit() {
  requestAnimationFrame(() => {
    requestAnimationFrame(applyOperatorAutoFit);
  });
}

function centerOperatorBoardOnCurrent() {
  const stage = els.operatorSteps.querySelector("[data-operator-board-stage]");
  const activeMarkers = operatorActiveMarkers();
  if (!stage || !activeMarkers.length) {
    return;
  }

  const bounds = operatorStageMarkerBounds(stage, activeMarkers);
  const markerCenterX = (bounds.left + bounds.right) / 2;
  const markerCenterY = (bounds.top + bounds.bottom) / 2;
  const targetLeft = clampScroll(markerCenterX - stage.clientWidth / 2, stage.scrollWidth - stage.clientWidth);
  const targetTop = clampScroll(markerCenterY - stage.clientHeight / 2, stage.scrollHeight - stage.clientHeight);
  stage.scrollTo({
    left: targetLeft,
    top: targetTop,
    behavior: "auto",
  });
}

function attachOperatorViewControls() {
  const root = els.operatorSteps;
  root.querySelector("[data-operator-back]")?.addEventListener("click", closeOperatorProject);
  root.querySelector("[data-operator-zoom]")?.addEventListener("input", (event) => {
    updateOperatorView({ zoom: Number(event.target.value) });
  });
  root.querySelector("[data-operator-marker-size]")?.addEventListener("input", (event) => {
    setOperatorMarkerSize(Number(event.target.value));
  });
  root.querySelectorAll("[data-operator-rotation]").forEach((button) => {
    button.addEventListener("click", () => updateOperatorView({ rotation: Number(button.dataset.operatorRotation) }));
  });
  root.querySelectorAll("[data-operator-marker]").forEach((button) => {
    button.addEventListener("click", () => updateOperatorView({ markerPalette: button.dataset.operatorMarker }));
  });
  root.querySelector("[data-operator-toggle-labels]")?.addEventListener("click", () => {
    updateOperatorView({ showLabels: !state.operatorView.showLabels });
  });
  root.querySelector("[data-operator-toggle-polarity]")?.addEventListener("click", () => {
    updateOperatorView({ showPolarity: !state.operatorView.showPolarity });
  });
  root.querySelector("[data-operator-toggle-contours]")?.addEventListener("click", () => {
    updateOperatorView({ showContours: !state.operatorView.showContours });
  });
  root.querySelectorAll("[data-operator-preview-image]").forEach((button) => {
    button.addEventListener("click", () => {
      state.operatorPreviewImage = button.dataset.operatorPreviewImage;
      renderOperatorSteps();
    });
  });
  root.querySelector("[data-close-operator-preview]")?.addEventListener("click", () => {
    state.operatorPreviewImage = null;
    renderOperatorSteps();
  });
  root.querySelector("[data-operator-preview-modal]")?.addEventListener("click", (event) => {
    if (event.target === event.currentTarget) {
      state.operatorPreviewImage = null;
      renderOperatorSteps();
    }
  });
  root.querySelector("[data-operator-focus]")?.addEventListener("click", () => {
    updateOperatorView({ focusMode: !state.operatorView.focusMode });
  });
  root.querySelector("[data-operator-fullscreen]")?.addEventListener("click", () => {
    const target = els.views.operator;
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else if (target?.requestFullscreen) {
      target.requestFullscreen();
    }
  });
  const boardImage = root.querySelector("[data-operator-board-stage] img");
  if (boardImage && !boardImage.complete) {
    boardImage.addEventListener("load", scheduleOperatorAutoFit, { once: true });
  }
}

function renderOperatorSteps() {
  if (els.operatorProjectBrowser) {
    els.operatorProjectBrowser.hidden = state.operatorWorkspaceOpen;
  }
  if (els.operatorWorkspace) {
    els.operatorWorkspace.hidden = !state.operatorWorkspaceOpen;
  }
  if (!state.operatorWorkspaceOpen) {
    els.operatorSteps.innerHTML = "";
    return;
  }
  if (!state.selectedProject) {
    els.operatorSteps.innerHTML = '<div class="muted">Wybierz projekt lub rozpocznij sesję.</div>';
    return;
  }
  if (!isOperatorProject(state.selectedProject)) {
    els.operatorSteps.innerHTML = '<div class="muted">Ten projekt jest jeszcze roboczy. Admin musi go przekazać do operatora.</div>';
    return;
  }
  const operatorSteps = operatorStepsForProject(state.selectedProject);
  if (!operatorSteps.length) {
    els.operatorSteps.innerHTML = '<div class="muted">Projekt nie ma jeszcze kroków.</div>';
    return;
  }

  const currentStep = resolveOperatorStep(operatorSteps);
  const currentIndex = operatorSteps.findIndex((step) => Number(step.id) === Number(currentStep.id));
  const event = latestEventForStep(currentStep.id);
  const status = operatorStepStatus(currentStep);
  const progress = operatorProgress(operatorSteps);
  const currentPoints = pointsForStep(state.selectedProject, currentStep);
  const currentPolarity = state.operatorView.showPolarity
    ? polarityItemsForStep(state.selectedProject, currentStep)
    : [];

  els.operatorSteps.innerHTML = `
    ${renderOperatorCommandBar(state.selectedProject, currentStep, progress)}
    <div class="operator-workstation">
      <section class="operator-board-panel">
        ${renderOperatorBoard(state.selectedProject, currentStep)}
      </section>
      <section class="operator-current-card ${status}">
        <div class="operator-step-head">
          <span>${currentIndex + 1} / ${operatorSteps.length}</span>
          <em class="operator-status ${status}">${escapeHtml(operatorStatusLabel(status))}</em>
        </div>
        <div class="operator-main-value">${escapeHtml(renderStepValue(currentStep))}</div>
        <div class="operator-detail-grid">
          <div><span>Indeks Medcom</span><strong>${escapeHtml(currentStep.medcom_index || "-")}</strong></div>
          <div><span>Ilość</span><strong>${escapeHtml(renderStepQuantity(currentStep))}</strong></div>
          <div><span>Punkty PCB</span><strong>${currentPoints.length || "-"}</strong></div>
          <div><span>Krok</span><strong>${currentStep.step_no}</strong></div>
        </div>
        <div class="operator-designators">
          <span>Desygnatory</span>
          ${renderStepPieces(currentStep)}
        </div>
        ${renderOperatorPolarityNotice(currentPolarity)}
        ${stepNotesWithoutSegments(currentStep) ? `<div class="operator-tech-note">${escapeHtml(stepNotesWithoutSegments(currentStep))}</div>` : ""}
        <label class="operator-note-field">
          Uwagi operatora
          <textarea rows="3" data-operator-note>${escapeHtml(event ? event.note : "")}</textarea>
        </label>
        <div class="operator-action-grid">
          <button type="button" class="operator-ok" data-operator-status="done">OK</button>
          <button type="button" class="operator-problem" data-operator-status="problem">Problem</button>
          <button type="button" data-operator-status="skipped">Pomiń</button>
        </div>
        <div class="operator-nav-actions">
          <button type="button" data-operator-prev ${currentIndex <= 0 ? "disabled" : ""}>Wstecz</button>
          <button type="button" data-operator-next ${currentIndex >= operatorSteps.length - 1 ? "disabled" : ""}>Dalej</button>
        </div>
      </section>
      ${renderOperatorStepList(operatorSteps, currentStep)}
    </div>
    ${renderOperatorPreviewModal(state.selectedProject)}
  `;

  els.operatorSteps.querySelectorAll("[data-operator-status]").forEach((button) => {
    button.addEventListener("click", () => {
      const note = els.operatorSteps.querySelector("[data-operator-note]")?.value || "";
      saveStepEvent(currentStep, button.dataset.operatorStatus, note);
    });
  });
  els.operatorSteps.querySelector("[data-operator-prev]")?.addEventListener("click", () => moveOperatorStep(-1));
  els.operatorSteps.querySelector("[data-operator-next]")?.addEventListener("click", () => moveOperatorStep(1));
  els.operatorSteps.querySelectorAll("[data-operator-jump-step]").forEach((button) => {
    button.addEventListener("click", () => {
      state.operatorActiveStepId = Number(button.dataset.operatorJumpStep);
      renderOperatorSteps();
    });
  });
  attachOperatorViewControls();
  updateOperatorHeader();
  scheduleOperatorAutoFit();
}

function moveOperatorStep(direction) {
  const steps = operatorStepsForProject(state.selectedProject);
  if (!steps.length) {
    return;
  }
  const currentIndex = Math.max(0, steps.findIndex((step) => Number(step.id) === Number(state.operatorActiveStepId)));
  const nextIndex = Math.max(0, Math.min(steps.length - 1, currentIndex + direction));
  state.operatorActiveStepId = steps[nextIndex].id;
  renderOperatorSteps();
}

function nextOpenOperatorStepId(steps, currentStep) {
  const currentIndex = steps.findIndex((step) => Number(step.id) === Number(currentStep.id));
  const after = steps.slice(currentIndex + 1).find((step) => !isOperatorStepHandled(step));
  if (after) {
    return after.id;
  }
  const before = steps.slice(0, currentIndex).find((step) => !isOperatorStepHandled(step));
  return before ? before.id : currentStep.id;
}

async function saveStepEvent(step, status, note) {
  if (state.selectedProject) {
    const payload = await api(`/api/projects/${state.selectedProject.id}/steps/${step.id}/operator-feedback`, {
      method: "POST",
      body: JSON.stringify({ status, note }),
    });
    state.selectedProject = payload.project;
    state.projects = state.projects.map((project) => (
      project.id === payload.project.id
        ? {
          ...project,
          ...payload.project,
          step_count: payload.project.steps?.length || project.step_count || 0,
          point_count: payload.project.points?.length || project.point_count || 0,
          open_feedback_count: (payload.project.operator_feedback || [])
            .filter((item) => ["open", "in_progress"].includes(item.admin_status)).length,
        }
        : project
    ));
    const steps = operatorStepsForProject(state.selectedProject);
    state.operatorActiveStepId = nextOpenOperatorStepId(steps, step);
    renderOperatorProjectList();
    renderOperatorSteps();
    return;
  }
  if (!state.currentSession) {
    alert("Najpierw rozpocznij sesję operatora.");
    return;
  }
  const payload = await api(`/api/sessions/${state.currentSession.id}/steps/${step.id}`, {
    method: "POST",
    body: JSON.stringify({ status, note }),
  });
  state.sessionEvents.set(Number(step.id), payload.event);
  const steps = operatorStepsForProject(state.selectedProject);
  state.operatorActiveStepId = nextOpenOperatorStepId(steps, step);
  renderOperatorSteps();
}

function renderSessionInfo() {
  if (!els.sessionInfo) {
    return;
  }
  els.views.operator?.classList.toggle("operator-session-active", Boolean(state.currentSession));
  if (!state.currentSession) {
    els.sessionInfo.textContent = "Brak aktywnej sesji.";
    return;
  }
  els.sessionInfo.innerHTML = `
    <strong>Sesja aktywna</strong><br>
    Operator: ${escapeHtml(state.currentSession.operator_name || "-")}<br>
    Stanowisko: ${escapeHtml(state.currentSession.station_name || "-")}<br>
    Start: ${escapeHtml(state.currentSession.started_at)}
  `;
}

function formatDate(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("pl-PL", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatNumber(value) {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  return Number(value).toLocaleString("pl-PL", { maximumFractionDigits: 3 });
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[char]));
}

els.navButtons.forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.view));
});

els.panelButtons.forEach((button) => {
  button.addEventListener("click", () => showActionPanel(button.dataset.panel));
});

els.closePanelButtons.forEach((button) => {
  button.addEventListener("click", hideActionPanels);
});

els.projectSearch.addEventListener("input", renderProjectTable);
els.refreshProjects.addEventListener("click", () => refreshData().catch((error) => alert(error.message)));
els.backToProjects?.addEventListener("click", showAdminProjectList);

els.importForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  els.importSummary.textContent = "Importuję pliki...";
  try {
    const payload = await apiForm("/api/import/prepared-xlsx", new FormData(els.importForm));
    renderImportSummary(payload.summary, payload.project);
    els.importForm.reset();
    hideActionPanels();
    await loadProjects();
    await selectProject(payload.project.id, "summary");
  } catch (error) {
    els.importSummary.textContent = error.message;
  }
});

els.projectForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = formData(els.projectForm);
  const response = await api("/api/projects", {
    method: "POST",
    body: JSON.stringify(data),
  });
  els.projectForm.reset();
  hideActionPanels();
  await loadProjects();
  await selectProject(response.project.id, "summary");
});

els.editProjectForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.selectedProject) {
    alert("Najpierw wybierz projekt.");
    return;
  }
  const data = formData(els.editProjectForm);
  const response = await api(`/api/projects/${state.selectedProject.id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
  hideActionPanels();
  await loadProjects();
  await selectProject(response.project.id, "summary");
});

els.boardImageForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.selectedProject) {
    alert("Najpierw wybierz projekt.");
    return;
  }
  try {
    const response = await apiForm(`/api/projects/${state.selectedProject.id}/board-image`, new FormData(els.boardImageForm));
    els.boardImageForm.reset();
    hideActionPanels();
    await loadProjects();
    await selectProject(response.project.id, "image");
  } catch (error) {
    alert(error.message);
  }
});

els.previewImagesForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.selectedProject) {
    alert("Najpierw wybierz projekt.");
    return;
  }
  const formDataValue = new FormData(els.previewImagesForm);
  const hasFile = Array.from(formDataValue.values()).some((value) => value instanceof File && value.size > 0);
  if (!hasFile) {
    alert("Wybierz przynajmniej jedno zdjęcie podglądu.");
    return;
  }
  try {
    const response = await apiForm(`/api/projects/${state.selectedProject.id}/preview-images`, formDataValue);
    els.previewImagesForm.reset();
    hideActionPanels();
    await loadProjects();
    await selectProject(response.project.id, "operatorPreviews");
  } catch (error) {
    alert(error.message);
  }
});

els.reimportForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.selectedProject) {
    alert("Najpierw wybierz projekt.");
    return;
  }
  els.reimportSummary.textContent = "Reimportuję dane...";
  try {
    const response = await apiForm(`/api/projects/${state.selectedProject.id}/import/prepared-xlsx`, new FormData(els.reimportForm));
    els.reimportSummary.textContent = `Utworzono ${response.summary.createdSteps} linii i ${response.summary.createdPoints} punktów.`;
    els.reimportForm.reset();
    hideActionPanels();
    await loadProjects();
    await selectProject(response.project.id, "lines");
  } catch (error) {
    els.reimportSummary.textContent = error.message;
  }
});

els.supplementPointsForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.selectedProject) {
    alert("Najpierw wybierz projekt.");
    return;
  }
  if (els.supplementPointsSummary) {
    els.supplementPointsSummary.textContent = "Uzupe\u0142niam punkty z P&P...";
  }
  try {
    const response = await apiForm(
      `/api/projects/${state.selectedProject.id}/points/import-pp`,
      new FormData(els.supplementPointsForm),
    );
    els.supplementPointsForm.reset();
    renderPointSupplementSummary(response.summary);
    state.activeProjectTab = "preview";
    state.selectedProject = response.project;
    await loadProjects();
    renderProjectDetails();
    renderOperatorSteps();
  } catch (error) {
    if (els.supplementPointsSummary) {
      els.supplementPointsSummary.textContent = error.message;
    } else {
      alert(error.message);
    }
  }
});

els.stepForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = formData(els.stepForm);
  await api(`/api/projects/${data.projectId}/steps`, {
    method: "POST",
    body: JSON.stringify(data),
  });
  els.stepForm.reset();
  hideActionPanels();
  await loadProjects();
  await selectProject(data.projectId, "lines");
});

els.pinIndexForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = formData(els.pinIndexForm);
  const payload = await api("/api/pin-indexes", {
    method: "POST",
    body: JSON.stringify(data),
  });
  state.pinIndexes = payload.pinIndexes || [];
  els.pinIndexForm.reset();
  renderPinIndexes();
  renderProjectDetails();
});

els.operatorProjectSearch?.addEventListener("input", renderOperatorProjectList);

window.addEventListener("resize", () => {
  if (state.activeView === "operator" && state.operatorWorkspaceOpen) {
    scheduleOperatorAutoFit();
  }
});

normalizeStaticLabels();

refreshData()
  .then(() => {
    renderOperatorProjectList();
    renderOperatorSteps();
    updateOperatorHeader();
  })
  .catch((error) => alert(error.message));
