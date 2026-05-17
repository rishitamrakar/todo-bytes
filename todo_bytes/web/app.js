// todo-bytes UI — vanilla JS, no build step.
//
// Organisation:
//   - state (one object, no globals scattered)
//   - api (thin wrappers around fetch)
//   - render (one function per UI region)
//   - actions (called from event handlers)
//   - boot (wire everything up on DOMContentLoaded)

// ---------- state ----------

const state = {
  projects: [],
  defaultProject: null,
  activeProject: null,
  // Top bar filters (orthogonal):
  //   activeDue: null | 'today' | 'tomorrow' | 'week' | 'next-week' | 'overdue' | 'no-due' | 'custom'
  //   activeTaskStatuses: Set of statuses to show. Default = all 5 (no filter).
  //   customRange: { from, to } when activeDue === 'custom'.
  activeDue: null,
  activeTaskStatuses: new Set(['todo', 'in-progress', 'done', 'hold', 'cancelled']),
  customRange: { from: null, to: null },
  tasks: [],
  editingTaskId: null,  // null = creating new task
  editingTaskProject: null,  // project the task being edited belongs to (needed in All Projects view)
  taskFormSnapshot: null,  // serialized form state on open; used to detect unsaved changes
  // Sidebar filters — status + tags. Both must pass for a project to show.
  // Default: active statuses; all tags + untagged checked.
  visibleStatuses: new Set(['todo', 'in-progress']),
  visibleTags: new Set(),  // populated from current projects on each refresh
  showUntagged: true,
  // Pending state — only mutated while a filter panel is open.
  // Committed to the visible* state on Apply, discarded on Cancel.
  pending: {
    statuses: null,
    tags: null,
    showUntagged: null,
    taskStatuses: null,
  },
};

const ALL_PROJECTS = '__all__';
const ALL_STATUS_VALUES = ['todo', 'in-progress', 'done', 'hold', 'cancelled'];


// ---------- UI state persistence ----------
//
// Persist filter / view selections to localStorage so a page refresh (or
// re-open) doesn't reset everything. We only save what the user *picks* —
// never task or project data (always re-fetched from the API).
//
// Key is versioned so we can change the saved shape later without crashing
// on old blobs — bump to :v2 and old state is silently ignored.

const UI_STATE_KEY = 'todo-bytes:ui-state:v1';
let uiStateLoaded = false;  // true after a successful loadUiState()

function saveUiState() {
  const snapshot = {
    activeProject: state.activeProject,
    activeDue: state.activeDue,
    activeTaskStatuses: [...state.activeTaskStatuses],
    customRange: state.customRange,
    visibleStatuses: [...state.visibleStatuses],
    visibleTags: [...state.visibleTags],
    showUntagged: state.showUntagged,
  };
  try {
    localStorage.setItem(UI_STATE_KEY, JSON.stringify(snapshot));
  } catch (err) {
    // Quota exceeded / storage disabled — not fatal, UI still works.
    console.warn('Could not save UI state:', err);
  }
}

function loadUiState() {
  const raw = localStorage.getItem(UI_STATE_KEY);
  if (!raw) return false;
  try {
    const s = JSON.parse(raw);
    if (typeof s.activeProject === 'string' || s.activeProject === null) {
      state.activeProject = s.activeProject;
    }
    if (s.activeDue === null || typeof s.activeDue === 'string') {
      state.activeDue = s.activeDue;
    }
    if (Array.isArray(s.activeTaskStatuses)) {
      state.activeTaskStatuses = new Set(s.activeTaskStatuses);
    }
    if (s.customRange && typeof s.customRange === 'object') {
      state.customRange = {
        from: s.customRange.from || null,
        to: s.customRange.to || null,
      };
    }
    if (Array.isArray(s.visibleStatuses)) {
      state.visibleStatuses = new Set(s.visibleStatuses);
    }
    if (Array.isArray(s.visibleTags)) {
      state.visibleTags = new Set(s.visibleTags);
    }
    if (typeof s.showUntagged === 'boolean') {
      state.showUntagged = s.showUntagged;
    }
    uiStateLoaded = true;
    return true;
  } catch (err) {
    console.warn('Bad UI state in localStorage, ignoring:', err);
    return false;
  }
}

// If the restored activeProject no longer exists (deleted in CLI between
// sessions), fall back to the default project so the UI isn't stuck on a
// dead project name.
function validateRestoredActiveProject() {
  if (!state.activeProject || state.activeProject === ALL_PROJECTS) return;
  const exists = state.projects.some(p => p.name === state.activeProject);
  if (!exists) state.activeProject = null;
}


// ---------- api ----------

const api = {
  async getProjects() {
    return fetchJson('/api/projects');
  },
  async getTasks(projectName, filters = {}) {
    const params = new URLSearchParams({ project: projectName });
    if (filters.due) params.set('due', filters.due);
    if (filters.due_from) params.set('due_from', filters.due_from);
    if (filters.due_to) params.set('due_to', filters.due_to);
    // Only send statuses when it's a real subset — omit means "pass through"
    if (filters.statuses && filters.statuses.length > 0
        && filters.statuses.length < ALL_STATUS_VALUES.length) {
      filters.statuses.forEach(s => params.append('statuses', s));
    }
    return fetchJson(`/api/tasks?${params}`);
  },
  async createTask(payload) {
    return fetchJson('/api/tasks', { method: 'POST', body: payload });
  },
  async updateTask(projectName, id, payload) {
    return fetchJson(`/api/tasks/${projectName}/${id}`, { method: 'PATCH', body: payload });
  },
  async deleteTask(projectName, id) {
    return fetchJson(`/api/tasks/${projectName}/${id}`, { method: 'DELETE' });
  },
  async markDone(projectName, id) {
    return fetchJson(`/api/tasks/${projectName}/${id}/done`, { method: 'POST' });
  },
  async reopen(projectName, id) {
    return fetchJson(`/api/tasks/${projectName}/${id}/reopen`, { method: 'POST' });
  },
  async moveTask(fromProject, id, toProject) {
    return fetchJson(`/api/tasks/${fromProject}/${id}/move`, {
      method: 'POST',
      body: { to_project: toProject },
    });
  },
  async reorder(projectName, ids) {
    return fetchJson(`/api/projects/${projectName}/reorder`, { method: 'POST', body: { ids } });
  },
  async createProject(name) {
    return fetchJson('/api/projects', { method: 'POST', body: { name } });
  },
  async getProject(name) {
    return fetchJson(`/api/projects/${encodeURIComponent(name)}`);
  },
  async updateProject(name, payload) {
    return fetchJson(`/api/projects/${encodeURIComponent(name)}`, { method: 'PATCH', body: payload });
  },
  async deleteProject(name) {
    return fetchJson(`/api/projects/${encodeURIComponent(name)}`, { method: 'DELETE' });
  },
};

async function fetchJson(url, opts = {}) {
  const { method = 'GET', body } = opts;
  const init = { method, headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) init.body = JSON.stringify(body);
  const res = await fetch(url, init);
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail || res.statusText);
  }
  if (res.status === 204) return null;
  return res.json();
}


// ---------- render: projects sidebar ----------

function visibleProjects() {
  return state.projects.filter(p =>
    state.visibleStatuses.has(p.status || 'todo') && projectPassesTagFilter(p)
  );
}

function projectPassesTagFilter(project) {
  const tags = project.tags || [];
  if (tags.length === 0) return state.showUntagged;
  return tags.some(t => state.visibleTags.has(t));
}

function renderProjectsNav() {
  const el = document.getElementById("projects-list");
  el.innerHTML = '';
  const projects = visibleProjects();
  projects.forEach(p => el.appendChild(buildProjectItem(p)));
  renderAllProjectsButton(projects);
}

function renderAllProjectsButton(visible) {
  const btn = document.getElementById('all-projects-btn');
  btn.classList.toggle('active', state.activeProject === ALL_PROJECTS);
  document.getElementById('all-count').textContent = `${visible.length}/${state.projects.length}`;
}

function renderTagFilter() {
  const el = document.getElementById('tag-filter-list');
  el.innerHTML = '';
  const allTags = collectAllTags();
  const hasUntagged = state.projects.some(p => !p.tags || p.tags.length === 0);

  // Render from pending state if the panel is open, else from actual state.
  // (Tag filter is dynamic so we always re-render rather than just sync.)
  const tagSet = state.pending.tags !== null ? state.pending.tags : state.visibleTags;
  const showUntagged = state.pending.showUntagged !== null ? state.pending.showUntagged : state.showUntagged;

  allTags.forEach(tag => el.appendChild(buildTagCheckbox(tag, tagSet.has(tag))));
  if (hasUntagged) el.appendChild(buildUntaggedCheckbox(showUntagged));
  if (allTags.length === 0 && !hasUntagged) {
    el.innerHTML = '<div style="color: var(--text-dim); font-size: 12px;">No tags yet. Add tags via project edit.</div>';
  }
}

function collectAllTags() {
  const set = new Set();
  state.projects.forEach(p => (p.tags || []).forEach(t => set.add(t)));
  return [...set].sort();
}

function buildTagCheckbox(tag, checked) {
  const lbl = document.createElement('label');
  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.checked = checked;
  cb.dataset.tag = tag;
  cb.addEventListener('change', () => {
    if (state.pending.tags === null) return;  // panel not open
    if (cb.checked) state.pending.tags.add(tag);
    else state.pending.tags.delete(tag);
  });
  lbl.appendChild(cb);
  lbl.appendChild(document.createTextNode(' ' + tag));
  return lbl;
}

function buildUntaggedCheckbox(checked) {
  const lbl = document.createElement('label');
  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.checked = checked;
  cb.addEventListener('change', () => {
    if (state.pending.showUntagged === null) return;  // panel not open
    state.pending.showUntagged = cb.checked;
  });
  lbl.appendChild(cb);
  const span = document.createElement('span');
  span.style.fontStyle = 'italic';
  span.style.color = 'var(--text-dim)';
  span.textContent = ' (no tag)';
  lbl.appendChild(span);
  return lbl;
}

function buildProjectItem(project) {
  const div = document.createElement('div');
  const status = project.status || 'todo';
  div.className = 'project-item status-' + status + (project.name === state.activeProject ? ' active' : '');
  div.innerHTML = `
    <span style="display:flex; align-items:center; flex:1;">
      <span class="project-status-dot"></span>
      ${escape(project.name)}
      ${project.name === state.defaultProject ? '<span class="default-mark">★</span>' : ''}
    </span>
    <button class="edit-btn" data-action="edit-project" title="Edit project">✎</button>
    <span class="count">${project.open}/${project.total}</span>
  `;
  div.addEventListener('click', e => {
    if (e.target.closest('[data-action="edit-project"]')) {
      e.stopPropagation();
      openEditProjectModal(project.name);
      return;
    }
    switchProject(project.name);
  });
  return div;
}


// ---------- render: top-bar chips ----------

const DUE_LABELS = {
  today: 'Today',
  tomorrow: 'Tomorrow',
  week: 'This week',
  'next-week': 'Next week',
  overdue: 'Overdue',
  'no-due': 'No due',
};

function renderViewTabs() {
  renderDueChip();
  renderTaskStatusChip();
  renderQuickAddVisibility();
}

function renderDueChip() {
  const btn = document.getElementById('due-filter-btn');
  const label = document.getElementById('due-chip-label');
  // Always use the "Due: <value>" format so the active choice is visible at
  // a glance — including 'Any', which means "no filter" but is still a
  // deliberate pick the user can see.
  if (state.activeDue === null) {
    btn.classList.remove('active');
    label.textContent = 'Due: Any';
  } else if (state.activeDue === 'custom' && state.customRange.from && state.customRange.to) {
    btn.classList.add('active');
    label.textContent = `Due: ${formatCustomRangeLabel(state.customRange.from, state.customRange.to)}`;
  } else {
    btn.classList.add('active');
    label.textContent = `Due: ${DUE_LABELS[state.activeDue] || state.activeDue}`;
  }
  // Highlight the matching option in the dropdown
  document.querySelectorAll('.due-option').forEach(opt => {
    const matches = (opt.dataset.due || null) === state.activeDue;
    opt.classList.toggle('active', matches);
  });
}

function renderTaskStatusChip() {
  const btn = document.getElementById('task-status-btn');
  const label = document.getElementById('task-status-chip-label');
  const total = ALL_STATUS_VALUES.length;
  const picked = state.activeTaskStatuses.size;
  // Always show the active selection — 'All' / 'None' / 'N of 5' — so the
  // chip reads as a value, not a label. Active style only when the picks
  // actually filter the task list (i.e. not 'All').
  if (picked === total) {
    btn.classList.remove('active');
    label.textContent = 'Status: All';
  } else if (picked === 0) {
    btn.classList.add('active');
    label.textContent = 'Status: None';
  } else {
    btn.classList.add('active');
    label.textContent = `Status: ${picked} of ${total}`;
  }
}

function renderQuickAddVisibility() {
  const isSingleProject = state.activeProject !== ALL_PROJECTS;
  const noDateFilter = state.activeDue === null;
  // Add task is allowed on any single-project view — the side panel lets you
  // pick the due date, so an active date filter doesn't matter.
  document.getElementById('quick-add-trigger').hidden = !isSingleProject;
  // Drag-reorder only makes sense on the unfiltered list (priority is
  // global, not per-filter), so the hint stays gated on "no date filter".
  document.getElementById('reorder-hint').hidden = !(isSingleProject && noDateFilter);
}

function formatCustomRangeLabel(fromIso, toIso) {
  // Compact: '5 May – 12 May' (or '5 May 2027 – ...' if year differs from current)
  const from = new Date(fromIso);
  const to = new Date(toIso);
  const opts = { day: 'numeric', month: 'short' };
  const sameYear = from.getFullYear() === to.getFullYear();
  const showYear = !sameYear || from.getFullYear() !== new Date().getFullYear();
  const fmt = (d) => d.toLocaleDateString(undefined, showYear ? { ...opts, year: 'numeric' } : opts);
  return `${fmt(from)} – ${fmt(to)}`;
}


// ---------- render: tasks list ----------

function renderTasks() {
  const container = document.getElementById('tasks');
  const empty = document.getElementById('empty-state');
  container.innerHTML = '';

  const tasks = visibleTasks();
  if (tasks.length === 0) {
    empty.hidden = false;
    return;
  }
  empty.hidden = true;

  // Grouped view when no specific due filter is picked. With a specific
  // filter (Today, This week, etc.) the section IS the filter — grouping
  // would just add a single-section wrapper, which is noise.
  if (state.activeDue === null) {
    renderGroupedTasks(container, tasks);
  } else {
    renderFlatTasks(container, tasks);
  }
}

function renderFlatTasks(container, tasks) {
  const ul = buildTaskList(tasks);
  container.appendChild(ul);
  // Drag-reorder is single-project only — priority is per-project.
  if (state.activeProject !== ALL_PROJECTS) {
    enableDragReorder(ul);
  }
}

function renderGroupedTasks(container, tasks) {
  const groups = groupTasksByDue(tasks);
  groups.forEach(g => container.appendChild(buildTaskSection(g)));
}

function buildTaskList(tasks) {
  const ul = document.createElement('ul');
  ul.className = 'tasks';
  tasks.forEach(t => ul.appendChild(buildTaskRow(t)));
  return ul;
}

function buildTaskSection(group) {
  const sec = document.createElement('section');
  sec.className = 'task-section';

  const header = document.createElement('div');
  header.className = 'section-header';
  header.innerHTML = `
    <span class="section-title ${group.cssClass}">${escape(group.label)}</span>
    <span class="section-count">${group.tasks.length}</span>
    <span class="section-divider"></span>
  `;
  sec.appendChild(header);

  const ul = buildTaskList(group.tasks);
  sec.appendChild(ul);

  // Within-section drag updates global priority but only reorders tasks
  // inside this section. Not available in All Projects (priority is per
  // project, can't span them).
  if (state.activeProject !== ALL_PROJECTS) {
    enableDragReorder(ul);
  }
  return sec;
}

// Buckets tasks into Overdue / Today / Tomorrow / This week / Later /
// No due date. Tasks land in exactly one bucket based on their due date,
// regardless of status (done tasks stay in their date bucket, rendered
// with strikethrough by existing CSS).
function groupTasksByDue(tasks) {
  const today = startOfDay(new Date());
  const tomorrow = addDays(today, 1);
  const weekEnd = addDays(today, 7);

  const buckets = {
    overdue:  { label: 'Overdue',     cssClass: 'overdue', tasks: [] },
    today:    { label: 'Today',       cssClass: 'today',   tasks: [] },
    tomorrow: { label: 'Tomorrow',    cssClass: '',        tasks: [] },
    week:     { label: 'This week',   cssClass: '',        tasks: [] },
    later:    { label: 'Later',       cssClass: '',        tasks: [] },
    nodue:    { label: 'No due date', cssClass: '',        tasks: [] },
  };

  for (const t of tasks) {
    bucketForTask(t, today, tomorrow, weekEnd, buckets).tasks.push(t);
  }

  return ['overdue','today','tomorrow','week','later','nodue']
    .map(k => buckets[k])
    .filter(b => b.tasks.length > 0);
}

function bucketForTask(task, today, tomorrow, weekEnd, buckets) {
  if (!task.due) return buckets.nodue;
  const due = startOfDay(new Date(task.due));
  if (due < today) return buckets.overdue;
  if (due.getTime() === today.getTime()) return buckets.today;
  if (due.getTime() === tomorrow.getTime()) return buckets.tomorrow;
  if (due < weekEnd) return buckets.week;
  return buckets.later;
}

function startOfDay(d) {
  const out = new Date(d);
  out.setHours(0, 0, 0, 0);
  return out;
}

function addDays(d, n) {
  const out = new Date(d);
  out.setDate(out.getDate() + n);
  return out;
}

function buildTaskRow(task) {
  const li = document.createElement('li');
  li.className = 'task ' + task.status;  // status used as a CSS modifier
  li.dataset.taskId = task.id;
  // In the All view, show project as a badge so user knows where each task is from.
  // In a single-project view, the project is implicit — hide the badge.
  const showProjectBadge = state.activeProject === ALL_PROJECTS;
  const hasContent = (task.description && task.description.trim()) || (task.notes && task.notes.trim());
  const tagsHtml = (task.tags || [])
    .map(t => `<span class="tag tag-${tagColorClass(t)}">${escape(t)}</span>`)
    .join('');
  const projectBadgeHtml = showProjectBadge && task.project
    ? `<span class="project-badge">${escape(task.project)}</span>`
    : '';
  li.innerHTML = `
    <span class="drag-handle" title="Drag to reorder">⋮⋮</span>
    <button class="status-circle" data-action="toggle-done" title="${statusTitle(task.status)}"></button>
    <div class="task-main">
      <span class="task-name">
        ${escape(task.name)}
        ${hasContent ? '<span class="has-content" title="Has description / notes" data-action="edit">📄</span>' : ''}
      </span>
      <div class="task-meta">
        ${tagsHtml ? `<span class="tags">${tagsHtml}</span>` : ''}
        ${projectBadgeHtml}
      </div>
    </div>
    <span class="due ${dueClass(task.due)}">${formatDue(task.due)}</span>
    <span class="actions">
      <button class="icon-btn" data-action="edit" title="Edit">✎</button>
      <button class="icon-btn danger" data-action="delete" title="Delete">✕</button>
    </span>
  `;
  wireTaskRowEvents(li, task);
  return li;
}

// Pick a tag colour deterministically from the tag string. Same tag name
// always gets the same colour — stable across reloads, no state to store.
// Purely cosmetic: no semantic meaning attached to the colours.
function tagColorClass(tag) {
  const palette = ['purple', 'blue', 'green', 'pink'];
  let hash = 0;
  for (let i = 0; i < tag.length; i++) {
    hash = ((hash << 5) - hash + tag.charCodeAt(i)) | 0;
  }
  return palette[Math.abs(hash) % palette.length];
}

function statusTitle(status) {
  const map = {
    'todo': 'Mark done',
    'in-progress': 'Mark done',
    'done': 'Click to un-do',
    'hold': 'On hold',
    'cancelled': 'Cancelled',
  };
  return map[status] || status;
}

function wireTaskRowEvents(li, task) {
  li.querySelector('.task-name').addEventListener('click', () => handleTaskNameClick(task));
  li.querySelector('.status-circle').addEventListener('click', e => {
    e.stopPropagation();
    toggleTaskDone(task);
  });
  li.querySelectorAll('.icon-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      handleTaskAction(btn.dataset.action, task);
    });
  });
}

function handleTaskAction(action, task) {
  if (action === 'edit') return openEditModal(task);
  if (action === 'delete') return deleteTask(task);
}


// ---------- drag-reorder ----------
//
// Each <ul class="tasks"> is its own Sortable instance. In flat view this is
// the entire task list; in grouped view there's one per section.
//
// Priority is a single global integer per task. A drag within a section only
// reorders tasks in that section relative to each other — tasks in other
// sections keep their priority positions. We achieve that by merging the
// section's new order back into the full project order before sending it
// to the server.

function enableDragReorder(ul) {
  Sortable.create(ul, {
    handle: '.drag-handle',
    animation: 150,
    onEnd: () => persistNewOrder(ul),
  });
}

async function persistNewOrder(ul) {
  const sectionIds = Array.from(ul.children).map(li => Number(li.dataset.taskId));
  const fullIds = mergeSectionIntoGlobalOrder(sectionIds);
  try {
    await api.reorder(state.activeProject, fullIds);
    // Keep state.tasks aligned with the new global priority order so the
    // next drag (in another section) sees the right baseline without an
    // extra fetch. Task objects' .priority field isn't read for rendering
    // in single-project view, so leaving it stale is fine.
    state.tasks = reorderTasksByIds(state.tasks, fullIds);
  } catch (err) {
    alert('Reorder failed: ' + err.message);
    await refreshTasks();
  }
}

// Walk the current global priority order. Whenever we hit a task that's
// part of the dragged section, replace it with the next ID from the new
// section order. Tasks outside the section keep their positions.
function mergeSectionIntoGlobalOrder(newSectionOrder) {
  const inSection = new Set(newSectionOrder);
  let cursor = 0;
  return state.tasks.map(t => {
    if (inSection.has(t.id)) return newSectionOrder[cursor++];
    return t.id;
  });
}

function reorderTasksByIds(tasks, ids) {
  const byId = new Map(tasks.map(t => [t.id, t]));
  return ids.map(id => byId.get(id)).filter(Boolean);
}


// ---------- actions ----------

async function refreshProjects() {
  const data = await api.getProjects();
  state.projects = data.projects;
  state.defaultProject = data.default;
  // Auto-include all discovered tags on first ever load (no saved state).
  // Once we have saved state, respect it — re-adding everything would undo
  // any tag the user explicitly removed via the filter panel.
  if (!uiStateLoaded) {
    collectAllTags().forEach(t => state.visibleTags.add(t));
  }
  validateRestoredActiveProject();
  if (!state.activeProject && state.projects.length > 0) {
    state.activeProject = state.defaultProject || state.projects[0].name;
  }
  renderProjectsNav();
  renderTagFilter();
  updateProjectTitle();
  renderStats();
}

async function refreshTasks() {
  if (!state.activeProject) return;
  // We always fetch with the status filter OFF — only the due filter goes
  // to the server. The status filter is applied client-side in renderTasks()
  // so it controls what's *shown* but not what counts toward progress.
  if (state.activeProject === ALL_PROJECTS) {
    state.tasks = await fetchAllVisibleTasks();
  } else {
    const data = await api.getTasks(state.activeProject, currentTaskFilters());
    state.tasks = data.tasks;
  }
  renderTasks();
  renderStats();
}

function currentTaskFilters() {
  // Status filter is applied client-side (see renderTasks / visibleTasks).
  // Only the due filter is sent to the server.
  const filters = {};
  if (state.activeDue) {
    filters.due = state.activeDue;
    if (state.activeDue === 'custom') {
      filters.due_from = state.customRange.from;
      filters.due_to = state.customRange.to;
    }
  }
  return filters;
}

function visibleTasks() {
  return state.tasks.filter(t => state.activeTaskStatuses.has(t.status));
}

async function fetchAllVisibleTasks() {
  const projects = visibleProjects();
  if (projects.length === 0) return [];
  const filters = currentTaskFilters();
  const results = await Promise.all(
    projects.map(p => api.getTasks(p.name, filters).catch(() => ({ tasks: [] })))
  );
  // Combine, then sort by due date then priority (most useful in cross-project view).
  return results
    .flatMap(r => r.tasks)
    .sort((a, b) => {
      const ad = a.due || '9999-12-31';
      const bd = b.due || '9999-12-31';
      if (ad !== bd) return ad < bd ? -1 : 1;
      return (a.priority || 0) - (b.priority || 0);
    });
}

function switchProject(name) {
  state.activeProject = name;
  saveUiState();
  renderProjectsNav();
  renderViewTabs();
  updateProjectTitle();
  renderStats();
  refreshTasks();
}

function switchToAllProjects() {
  state.activeProject = ALL_PROJECTS;
  saveUiState();
  renderProjectsNav();
  renderViewTabs();
  updateProjectTitle();
  renderStats();
  refreshTasks();
}

function pickDueOption(due) {
  // Single-select. Empty string ('Any') maps to null (no filter). Picks apply
  // immediately and close the dropdown.
  state.activeDue = due === '' ? null : due;
  if (state.activeDue !== 'custom') {
    state.customRange = { from: null, to: null };
  }
  saveUiState();
  closeAllTopBarPanels();
  renderViewTabs();
  refreshTasks();
}

function applyTaskStatusFilter() {
  if (state.pending.taskStatuses === null) return;
  state.activeTaskStatuses = state.pending.taskStatuses;
  state.pending.taskStatuses = null;
  saveUiState();
  document.getElementById('task-status-filter').hidden = true;
  renderViewTabs();
  // Status filter is purely client-side now — just re-render the list,
  // no server round-trip needed. Stats stay put (by design).
  renderTasks();
}

function openTaskStatusPanel() {
  closeAllTopBarPanels();
  state.pending.taskStatuses = new Set(state.activeTaskStatuses);
  syncTaskStatusCheckboxes();
  document.getElementById('task-status-filter').hidden = false;
}

function toggleTaskStatusPanel() {
  const panel = document.getElementById('task-status-filter');
  if (panel.hidden) openTaskStatusPanel();
  else closeAllTopBarPanels();
}

function syncTaskStatusCheckboxes() {
  document.querySelectorAll('#task-status-filter input[type=checkbox]').forEach(cb => {
    cb.checked = state.pending.taskStatuses.has(cb.dataset.taskStatus);
  });
}

function handleTaskStatusCheckboxChange(event) {
  const cb = event.target;
  if (cb.tagName !== 'INPUT' || state.pending.taskStatuses === null) return;
  const status = cb.dataset.taskStatus;
  if (cb.checked) state.pending.taskStatuses.add(status);
  else state.pending.taskStatuses.delete(status);
}

function handleTaskStatusAction(event) {
  const btn = event.target.closest('button[data-action]');
  if (!btn) return;
  if (btn.dataset.target !== 'task-status') return;
  if (btn.dataset.action === 'apply') applyTaskStatusFilter();
  else if (btn.dataset.action === 'select-all') {
    state.pending.taskStatuses = new Set(ALL_STATUS_VALUES);
    syncTaskStatusCheckboxes();
  }
}

function handleTaskStatusDblClick(event) {
  const btn = event.target.closest('button[data-action="select-all"]');
  if (!btn || btn.dataset.target !== 'task-status') return;
  state.pending.taskStatuses = new Set();
  syncTaskStatusCheckboxes();
}

// ---------- Due filter dropdown ----------

function openDueFilterPanel() {
  closeAllTopBarPanels();
  document.getElementById('custom-range-from').value = state.customRange.from || '';
  document.getElementById('custom-range-to').value = state.customRange.to || '';
  document.getElementById('due-filter-panel').hidden = false;
}

function toggleDueFilterPanel() {
  const panel = document.getElementById('due-filter-panel');
  if (panel.hidden) openDueFilterPanel();
  else closeAllTopBarPanels();
}

function applyCustomRange() {
  const from = document.getElementById('custom-range-from').value;
  const to = document.getElementById('custom-range-to').value;
  if (!from || !to) {
    alert('Pick both a start and end date.');
    return;
  }
  state.customRange = { from, to };
  state.activeDue = 'custom';
  saveUiState();
  closeAllTopBarPanels();
  renderViewTabs();
  refreshTasks();
}

function closeAllTopBarPanels() {
  document.getElementById('task-status-filter').hidden = true;
  document.getElementById('due-filter-panel').hidden = true;
  state.pending.taskStatuses = null;
}

function updateProjectTitle() {
  const title = state.activeProject === ALL_PROJECTS
    ? `All Projects (${visibleProjects().length} of ${state.projects.length})`
    : (state.activeProject || '—');
  document.getElementById("project-title").textContent = title;
}

// In All Projects view state.activeProject is the sentinel '__all__'. Task-level
// operations must target the task's own project, not the sentinel.
function projectForTask(task) {
  return state.activeProject === ALL_PROJECTS ? task.project : state.activeProject;
}

async function toggleTaskDone(task) {
  // Click the circle: done ↔ todo. Other statuses (hold, cancelled) need the modal.
  const project = projectForTask(task);
  if (task.status === 'done') {
    await api.reopen(project, task.id);
  } else if (task.status === 'todo' || task.status === 'in-progress') {
    await api.markDone(project, task.id);
  } else {
    return;  // hold, cancelled — use edit modal
  }
  await refreshProjects();
  await refreshTasks();
}

async function deleteTask(task) {
  if (!confirm(`Delete "${task.name}"?`)) return;
  await api.deleteTask(projectForTask(task), task.id);
  await refreshProjects();
  await refreshTasks();
}


// ---------- new project (inline in sidebar) ----------

async function handleNewProjectSubmit(event) {
  event.preventDefault();
  const input = document.getElementById('new-project-input');
  const name = input.value.trim();
  if (!name) return;
  try {
    await api.createProject(name);
  } catch (err) {
    alert('Create project failed: ' + err.message);
    return;
  }
  input.value = '';
  state.activeProject = name;
  await refreshProjects();
  await refreshTasks();
  input.focus();
}


// ---------- sidebar filters (status + tags) ----------
//
// Pending-apply model: opening a panel snapshots current state into
// state.pending. Checkboxes / Select all / Deselect all only mutate the
// pending state. The actual filter doesn't change until the user clicks
// Apply. Cancel (or closing the panel) discards.

function openFilterPanel(target) {
  closeAllFilterPanels();
  if (target === 'status') {
    state.pending.statuses = new Set(state.visibleStatuses);
    syncStatusCheckboxesFromPending();
  } else if (target === 'tag') {
    state.pending.tags = new Set(state.visibleTags);
    state.pending.showUntagged = state.showUntagged;
    renderTagFilter();  // renders from pending state
  }
  document.getElementById(`${target}-filter`).hidden = false;
  document.getElementById(`${target}-filter-btn`).classList.add('active');
}

function toggleFilterPanel(target) {
  const panel = document.getElementById(`${target}-filter`);
  if (panel.hidden) openFilterPanel(target);
  else closeAllFilterPanels();  // clicking the active chip closes (= cancel)
}

function closeAllFilterPanels() {
  document.querySelectorAll('.filter-panel').forEach(p => p.hidden = true);
  document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
  // Clear any pending state — closing without Apply discards
  state.pending.statuses = null;
  state.pending.tags = null;
  state.pending.showUntagged = null;
}

function handleStatusCheckboxChange(event) {
  const cb = event.target;
  if (cb.tagName !== 'INPUT') return;
  if (state.pending.statuses === null) return;  // panel not open
  const status = cb.dataset.status;
  if (cb.checked) state.pending.statuses.add(status);
  else state.pending.statuses.delete(status);
}

function syncStatusCheckboxesFromPending() {
  document.querySelectorAll('#status-filter input[type=checkbox]').forEach(cb => {
    cb.checked = state.pending.statuses.has(cb.dataset.status);
  });
}

function handleFilterAction(event) {
  const btn = event.target.closest('button[data-action]');
  if (!btn) return;
  const action = btn.dataset.action;
  const target = btn.dataset.target;
  if (action === 'apply') applyFilter(target);
  else if (action === 'select-all') selectAllInPending(target);
}

// Double-click on Select all = deselect all. Single-click selects, dblclick
// fires after a brief select-all flicker which doubles as visual feedback.
function handleFilterDblClick(event) {
  const btn = event.target.closest('button[data-action="select-all"]');
  if (!btn) return;
  deselectAllInPending(btn.dataset.target);
}

function selectAllInPending(target) {
  if (target === 'status') {
    state.pending.statuses = new Set(ALL_STATUS_VALUES);
    syncStatusCheckboxesFromPending();
  } else if (target === 'tag') {
    state.pending.tags = new Set(collectAllTags());
    state.pending.showUntagged = true;
    renderTagFilter();
  }
}

function deselectAllInPending(target) {
  if (target === 'status') {
    state.pending.statuses = new Set();
    syncStatusCheckboxesFromPending();
  } else if (target === 'tag') {
    state.pending.tags = new Set();
    state.pending.showUntagged = false;
    renderTagFilter();
  }
}

function applyFilter(target) {
  if (target === 'status' && state.pending.statuses !== null) {
    state.visibleStatuses = state.pending.statuses;
  } else if (target === 'tag' && state.pending.tags !== null) {
    state.visibleTags = state.pending.tags;
    state.showUntagged = state.pending.showUntagged;
  }
  saveUiState();
  closeAllFilterPanels();
  renderProjectsNav();
  // If the active project is now filtered out, fall back to All Projects view
  if (state.activeProject && state.activeProject !== ALL_PROJECTS) {
    const stillVisible = visibleProjects().some(p => p.name === state.activeProject);
    if (!stillVisible) switchToAllProjects();
  }
}


// ---------- modal: edit project ----------

async function openEditProjectModal(projectName) {
  let project;
  try {
    project = await api.getProject(projectName);
  } catch (err) {
    alert('Could not load project: ' + err.message);
    return;
  }
  const form = document.getElementById('project-form');
  form.elements.name.value = project.name;
  form.elements.description.value = project.description || '';
  form.elements.status.value = project.status || 'todo';
  const { date: pDate, time: pTime } = splitDueIso(project.due);
  form.elements.due_date.value = pDate;
  form.elements.due_time.value = pTime;
  form.elements.tags.value = (project.tags || []).join(', ');
  form.dataset.editing = projectName;
  showModal('project-modal');
}

async function submitProjectForm(event) {
  event.preventDefault();
  const form = event.target;
  const name = form.dataset.editing;
  const tags = (form.elements.tags.value || '')
    .split(',')
    .map(s => s.trim())
    .filter(Boolean);
  const payload = {
    description: form.elements.description.value.trim() || null,
    status: form.elements.status.value,
    due: combineDateTimeToIso(form.elements.due_date.value, form.elements.due_time.value),
    tags,
  };
  try {
    await api.updateProject(name, payload);
  } catch (err) {
    alert('Save failed: ' + err.message);
    return;
  }
  hideModal('project-modal');
  await refreshProjects();
}

async function deleteActiveProject() {
  const form = document.getElementById('project-form');
  const name = form.dataset.editing;
  if (!confirm(`Delete project "${name}" and all its tasks?`)) return;
  try {
    await api.deleteProject(name);
  } catch (err) {
    alert('Delete failed: ' + err.message);
    return;
  }
  hideModal('project-modal');
  if (state.activeProject === name) state.activeProject = null;
  await refreshProjects();
  await refreshTasks();
}


// ---------- modal: edit task ----------

function handleTaskNameClick(task) {
  const modalOpen = !document.getElementById('task-modal').hidden;
  // Click same task again → toggle close (Notion-style)
  if (modalOpen && state.editingTaskId === task.id) {
    tryCloseTaskPanel();
    return;
  }
  // Click different task while editing → ask before discarding, then switch
  if (modalOpen && taskFormIsDirty()) {
    if (!window.confirm('Discard unsaved changes?')) return;
  }
  openEditModal(task);
}

function openEditModal(task) {
  state.editingTaskId = task.id;
  state.editingTaskProject = projectForTask(task);
  document.getElementById('modal-title').textContent = 'Edit task';
  fillTaskForm(task);
  showModal('task-modal');
  state.taskFormSnapshot = snapshotTaskForm();
  attachOutsideClickListenerOnNextTick();
}

function openCreateModal() {
  // Default to active project; in All Projects view fall back to the default project.
  const targetProject = state.activeProject === ALL_PROJECTS
    ? state.defaultProject
    : state.activeProject;
  if (!targetProject) {
    alert('Pick a project first.');
    return;
  }
  state.editingTaskId = null;
  state.editingTaskProject = targetProject;
  document.getElementById('modal-title').textContent = 'New task';
  fillTaskForm({
    name: '',
    due: null,
    tags: [],
    status: 'todo',
    description: '',
    notes: '',
    project: targetProject,
    created: null,
  });
  showModal('task-modal');
  state.taskFormSnapshot = snapshotTaskForm();
  attachOutsideClickListenerOnNextTick();
  document.getElementById('task-form').elements.name.focus();
}

function attachOutsideClickListenerOnNextTick() {
  setTimeout(() => {
    document.addEventListener('mousedown', handleOutsideClickToClose);
  }, 0);
}

function handleOutsideClickToClose(e) {
  const modal = document.getElementById('task-modal');
  if (modal.hidden) {
    document.removeEventListener('mousedown', handleOutsideClickToClose);
    return;
  }
  if (modal.contains(e.target)) return;  // click inside the panel
  // Let task-row clicks be handled by handleTaskNameClick (toggle/switch logic)
  if (e.target.closest('.task-name') || e.target.closest('.task')) return;
  tryCloseTaskPanel();
}

function snapshotTaskForm() {
  const form = document.getElementById('task-form');
  return JSON.stringify(readTaskForm(form)) + '|' + form.elements.project.value;
}

function taskFormIsDirty() {
  if (state.taskFormSnapshot === null) return false;
  return snapshotTaskForm() !== state.taskFormSnapshot;
}

function tryCloseTaskPanel() {
  if (!taskFormIsDirty()) {
    closeTaskPanelAnimated();
    return;
  }
  if (window.confirm('Discard unsaved changes?')) {
    closeTaskPanelAnimated();
  }
}

function closeTaskPanelAnimated() {
  const modal = document.getElementById('task-modal');
  if (modal.hidden) return;
  modal.classList.add('closing');
  const card = modal.querySelector('.modal-card');
  card.addEventListener('animationend', function onEnd() {
    card.removeEventListener('animationend', onEnd);
    modal.classList.remove('closing');
    modal.hidden = true;
  }, { once: true });
}

function fillTaskForm(task) {
  const form = document.getElementById('task-form');
  form.elements.name.value = task.name || '';
  const { date: dueDate, time: dueTime } = splitDueIso(task.due);
  form.elements.due_date.value = dueDate;
  form.elements.due_time.value = dueTime;
  form.elements.tags.value = (task.tags || []).join(', ');
  form.elements.status.value = task.status || 'todo';
  form.elements.description.value = task.description || '';
  form.elements.notes.value = task.notes || '';
  populateProjectDropdown(form.elements.project, task.project);
  document.getElementById('meta-created').textContent = task.created || '—';
  // Auto-open notes if the task has notes; collapse otherwise.
  document.getElementById('notes-details').open = Boolean((task.notes || '').trim());
}

function populateProjectDropdown(select, currentProject) {
  select.innerHTML = '';
  state.projects.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p.name;
    opt.textContent = p.name;
    if (p.name === currentProject) opt.selected = true;
    select.appendChild(opt);
  });
}

async function submitTaskForm(event) {
  event.preventDefault();
  const form = event.target;
  const targetProject = form.elements.project.value;
  const payload = readTaskForm(form);
  if (!payload.name) {
    alert('Task name is required.');
    return;
  }
  try {
    if (state.editingTaskId === null) {
      await api.createTask({ project: targetProject, ...payload });
    } else {
      await saveTaskEdits(state.editingTaskProject, state.editingTaskId, targetProject, payload);
    }
  } catch (err) {
    alert('Save failed: ' + err.message);
    return;
  }
  closeTaskPanelAnimated();
  await refreshProjects();
  await refreshTasks();
}

async function saveTaskEdits(sourceProject, taskId, targetProject, payload) {
  if (targetProject && targetProject !== sourceProject) {
    const moved = await api.moveTask(sourceProject, taskId, targetProject);
    await api.updateTask(targetProject, moved.id, payload);
    return;
  }
  await api.updateTask(sourceProject, taskId, payload);
}

function readTaskForm(form) {
  const tags = form.elements.tags.value
    .split(',')
    .map(s => s.trim())
    .filter(Boolean);
  return {
    name: form.elements.name.value.trim(),
    due: combineDateTimeToIso(form.elements.due_date.value, form.elements.due_time.value),
    tags,
    status: form.elements.status.value,
    description: form.elements.description.value.trim() || null,
    notes: form.elements.notes.value || null,
    // project handled separately via moveTask if changed
  };
}


// ---------- modal helpers ----------

function showModal(id) { document.getElementById(id).hidden = false; }
function hideModal(id) { document.getElementById(id).hidden = true; }


// ---------- utils ----------

function escape(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// `due` arrives from the server as an ISO datetime string (e.g. 2026-05-10T23:59:59).
// If the time is end-of-day (23:59), show just the date — cleaner. Otherwise show date + time.
function formatDue(iso) {
  if (!iso) return '';
  const datePart = iso.slice(0, 10);
  const timePart = iso.slice(11, 16);  // HH:MM
  if (timePart === '23:59') return datePart;
  return `${datePart} ${timePart}`;
}

function dueClass(iso) {
  if (!iso) return '';
  const datePart = iso.slice(0, 10);
  const today = new Date().toISOString().slice(0, 10);
  if (datePart < today) return 'overdue';
  if (datePart === today) return 'today';
  return '';
}

// We split datetime into separate date + time inputs (native datetime-local
// has no explicit Apply button, which is confusing). Time is optional — if
// the user leaves it empty we default to end-of-day (23:59).
function splitDueIso(iso) {
  if (!iso) return { date: '', time: '' };
  const datePart = iso.slice(0, 10);
  const timePart = iso.slice(11, 16);  // HH:MM
  // Hide the default end-of-day time — it's just our convention, not
  // something the user picked.
  if (timePart === '23:59') return { date: datePart, time: '' };
  return { date: datePart, time: timePart };
}

function combineDateTimeToIso(dateStr, timeStr) {
  if (!dateStr) return null;
  const time = timeStr || '23:59:59';  // end-of-day default when no time given
  // Ensure seconds are present
  const fullTime = time.length === 5 ? time + ':00' : time;
  return `${dateStr}T${fullTime}`;
}

// Update the stats card in the side pane.
// Progress reflects the due-filtered task set but IGNORES the status filter.
// Reasoning: due filter is "what slice of work I'm focusing on" (today /
// this week / overdue) — progress on that slice is useful. Status filter
// is just visibility (hide done from the list) — it shouldn't change the
// completion %, otherwise hiding done would always read as 0% done.
function renderStats() {
  const { open, done } = countOpenDone(state.tasks);
  const total = open + done;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  document.getElementById('stat-open').textContent = open;
  document.getElementById('stat-done').textContent = done;
  document.getElementById('stat-pct').textContent = pct + '%';
  document.getElementById('progress-fill').style.width = pct + '%';
}

function countOpenDone(tasks) {
  // Mirrors backend project_summary: only todo + in-progress count as open;
  // done counts as done; hold + cancelled are excluded from both, so they
  // don't drag the completion percentage down.
  let open = 0, done = 0;
  for (const t of tasks) {
    if (t.status === 'done') done++;
    else if (t.status === 'todo' || t.status === 'in-progress') open++;
  }
  return { open, done };
}


// ---------- theme ----------
//
// CSS variables drive everything; we just toggle data-theme on <html>.
// Saved choice in localStorage wins; otherwise follow prefers-color-scheme.

const THEME_KEY = 'todo-bytes:theme';
const SUN = '☀';
const MOON = '☾';

function resolveInitialTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === 'light' || saved === 'dark') return saved;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  const btn = document.getElementById('theme-toggle');
  if (btn) btn.textContent = theme === 'dark' ? SUN : MOON;
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'light';
  const next = current === 'dark' ? 'light' : 'dark';
  localStorage.setItem(THEME_KEY, next);
  applyTheme(next);
}


// ---------- boot ----------

// Apply the theme as early as possible to avoid a light-flash on dark loads.
applyTheme(resolveInitialTheme());

document.addEventListener('DOMContentLoaded', async () => {
  // Top-bar Due dropdown (single-select)
  document.getElementById('due-filter-btn').addEventListener('click', toggleDueFilterPanel);
  document.querySelectorAll('.due-option').forEach(opt => {
    opt.addEventListener('click', () => pickDueOption(opt.dataset.due));
  });
  document.getElementById('custom-range-apply').addEventListener('click', applyCustomRange);

  // Top-bar task status multiselect
  document.getElementById('task-status-btn').addEventListener('click', toggleTaskStatusPanel);
  document.getElementById('task-status-filter').addEventListener('change', handleTaskStatusCheckboxChange);
  document.getElementById('task-status-filter').addEventListener('click', handleTaskStatusAction);
  document.getElementById('task-status-filter').addEventListener('dblclick', handleTaskStatusDblClick);

  // Task modal
  document.getElementById('modal-cancel').addEventListener('click', tryCloseTaskPanel);
  document.getElementById('task-form').addEventListener('submit', submitTaskForm);

  // Esc closes any open modal (asks before discarding unsaved task changes)
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    if (!document.getElementById('task-modal').hidden) tryCloseTaskPanel();
    hideModal('project-modal');
  });



  // Quick-add trigger — clicking the row opens the full new-task panel.
  document.getElementById('quick-add-trigger').addEventListener('click', openCreateModal);

  // Inline new-project form (sidebar)
  document.getElementById('new-project-form').addEventListener('submit', handleNewProjectSubmit);

  // Sidebar filters — chips toggle panels; panel buttons handle actions
  document.getElementById('status-filter-btn').addEventListener('click', () => toggleFilterPanel('status'));
  document.getElementById('tag-filter-btn').addEventListener('click', () => toggleFilterPanel('tag'));
  document.getElementById('status-filter').addEventListener('change', handleStatusCheckboxChange);
  document.getElementById('status-filter').addEventListener('click', handleFilterAction);
  document.getElementById('status-filter').addEventListener('dblclick', handleFilterDblClick);
  document.getElementById('tag-filter').addEventListener('click', handleFilterAction);
  document.getElementById('tag-filter').addEventListener('dblclick', handleFilterDblClick);

  // Theme toggle (also re-syncs the icon since the button didn't exist when applyTheme ran early)
  applyTheme(document.documentElement.getAttribute('data-theme') || 'light');
  document.getElementById('theme-toggle').addEventListener('click', toggleTheme);

  // 'All Projects' button at the top of the sidebar
  document.getElementById('all-projects-btn').addEventListener('click', switchToAllProjects);

  // Project edit modal
  document.getElementById('project-cancel').addEventListener('click', () => hideModal('project-modal'));
  document.getElementById('project-form').addEventListener('submit', submitProjectForm);
  document.getElementById('project-delete').addEventListener('click', deleteActiveProject);

  // Restore saved filters / selections before the first render so the UI
  // boots in the user's last view instead of defaults.
  loadUiState();

  renderViewTabs();
  await refreshProjects();
  await refreshTasks();
});
