local AEROSPACE_PATH = "/opt/homebrew/bin/aerospace"

local overview = nil
local escapeHotkey = nil
local workspaceHotkeys = {}
local overviewTasks = {}
local overviewRequestId = 0

local function trim(s)
  return (s:gsub("^%s*(.-)%s*$", "%1"))
end

local function htmlEscape(s)
  s = s or ""
  s = s:gsub("&", "&amp;")
  s = s:gsub("<", "&lt;")
  s = s:gsub(">", "&gt;")
  s = s:gsub('"', "&quot;")
  s = s:gsub("'", "&#39;")
  return s
end

local function parseWorkspaceNames(output)
  local names = {}

  for line in (output or ""):gmatch("[^\r\n]+") do
    local workspace = trim(line)
    if workspace ~= "" then
      table.insert(names, workspace)
    end
  end

  return names
end

local function parseWindows(output)
  local workspaces = {}

  for line in (output or ""):gmatch("[^\r\n]+") do
    local workspace, app, title =
      line:match("^([^\t]*)\t([^\t]*)\t(.*)$")

    if workspace and workspace ~= "" then
      if not workspaces[workspace] then
        workspaces[workspace] = {}
      end

      table.insert(workspaces[workspace], {
        app = app,
        title = title
      })
    end
  end

  return workspaces
end

local function sortedWorkspaceNames(workspaces)
  local names = {}

  for ws, _ in pairs(workspaces) do
    table.insert(names, ws)
  end

  table.sort(names, function(a, b)
    local na = tonumber(a)
    local nb = tonumber(b)

    if na and nb then
      return na < nb
    end

    if na then return true end
    if nb then return false end

    return a < b
  end)

  return names
end

local function buildHTML(
  workspaces,
  focusedWorkspace,
  columns,
  loadingWindows,
  loadingWorkspaces
)
  local cards = {}

  for _, ws in ipairs(sortedWorkspaceNames(workspaces)) do
    local windows = workspaces[ws]
    local rows = {}

    for _, win in ipairs(windows) do
      table.insert(rows, string.format([[
        <div class="window">
          <div class="app">%s</div>
          <div class="title">%s</div>
        </div>
      ]],
        htmlEscape(win.app),
        htmlEscape(win.title)
      ))
    end

    if loadingWindows and #rows == 0 then
      table.insert(rows, [[
        <div class="loading-windows">Loading windows…</div>
      ]])
    end

    local focusedClass = ""
    if ws == focusedWorkspace then
      focusedClass = " focused"
    end

    table.insert(cards, string.format([[
      <a class="workspace%s" href="aerospace://workspace/%s">
        <div class="workspace-header">
          <div class="workspace-number">%s</div>
          <div class="window-count">%s</div>
        </div>

        <div class="windows">
          %s
        </div>
      </a>
    ]],
      focusedClass,
      htmlEscape(ws),
      htmlEscape(ws),
      loadingWindows and "loading…" or (#windows .. " windows"),
      table.concat(rows, "\n")
    ))
  end

  local gridContent = table.concat(cards, "\n")

  if #cards == 0 then
    if loadingWorkspaces then
      gridContent = [[
        <div class="loading-state">
          <div class="loading-spinner"></div>
          <div>Loading workspaces…</div>
        </div>
      ]]
    else
      gridContent = [[
        <div class="loading-state">No workspaces found</div>
      ]]
    end
  end

  return string.format([[
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">

<style>
  * {
    box-sizing: border-box;
  }

  html, body {
    margin: 0;
    padding: 0;
    width: 100%%;
    height: 100%%;
    overflow: hidden;

    font-family:
      -apple-system,
      BlinkMacSystemFont,
      "SF Pro Display",
      "Helvetica Neue",
      sans-serif;

    color: #f4f4f5;
  }

  body {
    background:
      linear-gradient(
        145deg,
        rgba(28, 28, 32, 0.96),
        rgba(12, 12, 15, 0.96)
      );

    padding: 28px;
  }

  .header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 22px;
  }

  .header-title {
    font-size: 22px;
    font-weight: 700;
    letter-spacing: -0.4px;
  }

  .hint {
    color: rgba(255,255,255,0.45);
    font-size: 12px;
  }

  .grid {
    display: grid;
    grid-template-columns:
      repeat(%d, minmax(0, 1fr));
  
    gap: 14px;
  
    align-items: start;
    grid-auto-rows: max-content;
  
    max-height: calc(100%% - 50px);
    overflow-y: auto;
  
    padding-right: 4px;
  }

  .workspace {
    display: block;
    text-decoration: none;
    color: inherit;

    border-radius: 14px;

    background:
      rgba(255,255,255,0.055);

    border:
      1px solid rgba(255,255,255,0.08);

    padding: 16px;

    min-height: 0;
    height: max-content;

    transition:
      background 100ms ease,
      border 100ms ease,
      transform 100ms ease;
  }

  .workspace:hover {
    background:
      rgba(255,255,255,0.09);

    border-color:
      rgba(255,255,255,0.18);

    transform: translateY(-1px);
  }

  .workspace.focused {
    border:
      1px solid rgba(125, 190, 255, 0.75);

    background:
      rgba(100, 170, 255, 0.12);
  }

  .loading-state {
    grid-column: 1 / -1;
    min-height: 70px;

    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;

    color: rgba(255,255,255,0.62);
    font-size: 13px;
  }

  .loading-spinner {
    width: 16px;
    height: 16px;
    border-radius: 50%%;
    border: 2px solid rgba(255,255,255,0.18);
    border-top-color: rgba(125,190,255,0.90);
    animation: spin 700ms linear infinite;
  }

  .loading-windows {
    padding: 5px 3px;
    color: rgba(255,255,255,0.35);
    font-size: 12px;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .workspace-header {
    display: flex;
    align-items: center;
    justify-content: space-between;

    padding-bottom: 10px;
    margin-bottom: 5px;

    border-bottom:
      1px solid rgba(255,255,255,0.07);
  }

  .workspace-number {
    font-size: 18px;
    font-weight: 700;
  }

  .window-count {
    font-size: 11px;
    color: rgba(255,255,255,0.42);
  }

  .windows {
    margin-top: 8px;
  }

  .window {
    display: grid;

    grid-template-columns:
      minmax(90px, 120px)
      minmax(0, 1fr);

    gap: 10px;

    padding: 5px 3px;

    font-size: 12px;
    line-height: 1.25;
  }

  .app {
    font-weight: 600;
    color: rgba(255,255,255,0.88);

    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .title {
    color: rgba(255,255,255,0.55);

    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  ::-webkit-scrollbar {
    width: 7px;
  }

  ::-webkit-scrollbar-thumb {
    border-radius: 10px;
    background: rgba(255,255,255,0.15);
  }
</style>
</head>

<body>

<div class="header">
  <div class="header-title">AeroSpace</div>
  <div class="hint">number to switch · click workspace · esc to close</div>
</div>

<div class="grid">
  %s
</div>

</body>
</html>
]], columns, gridContent)
end

local function clearWorkspaceHotkeys()
  for _, hotkey in ipairs(workspaceHotkeys) do
    hotkey:disable()
  end
  workspaceHotkeys = {}
end

local function hideOverview()
  -- Invalidate asynchronous callbacks before terminating their tasks.
  overviewRequestId = overviewRequestId + 1

  if escapeHotkey then
    escapeHotkey:disable()
    escapeHotkey = nil
  end

  clearWorkspaceHotkeys()

  for _, task in ipairs(overviewTasks) do
    if task:isRunning() then
      task:terminate()
    end
  end
  overviewTasks = {}

  if overview then
    overview:delete()
    overview = nil
  end
end

local function switchToWorkspace(workspace)
  hs.task.new(
    AEROSPACE_PATH,
    function()
      hideOverview()
    end,
    { "workspace", workspace }
  ):start()
end

local function calculateOverviewSize(workspaces, frame)
  local names = sortedWorkspaceNames(workspaces)
  local workspaceCount = #names

  -- Layout tuning
  local maxColumns = 4
  local cardWidth = 320
  local gap = 14

  -- Corresponds approximately to the CSS dimensions
  local bodyPadding = 28
  local headerHeight = 48
  local cardHeaderHeight = 48
  local windowRowHeight = 26
  local cardPadding = 16

  -- Keep one grid column when there are no windows/workspaces so the CSS and
  -- row calculation remain valid.
  local columns = math.max(1, math.min(workspaceCount, maxColumns))
  local rows = math.ceil(workspaceCount / columns)

  -- Calculate the required height of each grid row.
  -- A CSS grid row is as tall as its tallest card.
  local rowHeights = {}

  for index, ws in ipairs(names) do
    local row = math.ceil(index / columns)
    local windowCount = #workspaces[ws]

    local cardHeight =
      cardPadding * 2 +
      cardHeaderHeight +
      windowCount * windowRowHeight

    rowHeights[row] = math.max(
      rowHeights[row] or 0,
      cardHeight
    )
  end

  local width =
    bodyPadding * 2 +
    columns * cardWidth +
    (columns - 1) * gap

  local height =
    bodyPadding * 2 +
    headerHeight +
    math.max(0, rows - 1) * gap

  for _, rowHeight in ipairs(rowHeights) do
    height = height + rowHeight
  end

  -- Don't let the overview become larger than the monitor.
  width = math.min(width, frame.w * 0.92)
  height = math.min(height, frame.h * 0.90)

  -- Sensible minimum
  width = math.max(width, 400)
  height = math.max(height, 180)

  return width, height, columns
end

local function logOverviewTiming(state, event)
  local elapsedMs =
    (hs.timer.absoluteTime() - state.startedAt) / 1000000

  print(string.format(
    "[AeroSpace overview] %s: %.1f ms",
    event,
    elapsedMs
  ))
end

local function overviewIsCurrent(state)
  return overview ~= nil and
    overviewRequestId == state.requestId
end

local function setOverviewContent(state, html, timingLabel)
  if not overviewIsCurrent(state) then
    return
  end

  local _, navigationId = overview:html(html)

  if timingLabel and navigationId then
    state.navigationTimings[navigationId] = timingLabel
  end
end

local function updateWorkspaceHotkeys(workspaces)
  clearWorkspaceHotkeys()

  for _, ws in ipairs(sortedWorkspaceNames(workspaces)) do
    if ws:match("^%d$") then
      local workspace = ws
      local hotkey = hs.hotkey.new({}, workspace, function()
        switchToWorkspace(workspace)
      end)

      hotkey:enable()
      table.insert(workspaceHotkeys, hotkey)
    end
  end
end

local function renderOverview(state)
  if not overviewIsCurrent(state) then
    return
  end

  local width, height, columns =
    calculateOverviewSize(state.workspaces, state.frame)

  local x = state.frame.x + (state.frame.w - width) / 2
  local y = state.frame.y + (state.frame.h - height) / 2

  overview:frame({
    x = x,
    y = y,
    w = width,
    h = height
  })

  updateWorkspaceHotkeys(state.workspaces)

  local timingLabel = nil
  local fullyLoaded =
    state.workspaceListFinished and
    state.focusedWorkspaceFinished and
    state.windowsFinished

  if fullyLoaded and not state.finalRenderQueued then
    state.finalRenderQueued = true
    timingLabel = "full overview rendered"
  end

  setOverviewContent(
    state,
    buildHTML(
      state.workspaces,
      state.focusedWorkspace,
      columns,
      not state.windowsFinished,
      not state.workspaceListFinished
    ),
    timingLabel
  )
end

local function logOverviewTaskError(label, exitCode, stdErr)
  local message = trim(stdErr or "")
  if message == "" then
    message = "no error output"
  end

  print(string.format(
    "[AeroSpace overview] %s failed (exit %d): %s",
    label,
    exitCode,
    message
  ))
end

local function startOverviewTask(state, label, arguments, callback)
  local task = hs.task.new(
    AEROSPACE_PATH,
    function(exitCode, stdOut, stdErr)
      if not overviewIsCurrent(state) then
        return
      end

      if exitCode ~= 0 then
        logOverviewTaskError(label, exitCode, stdErr)
      end

      callback(exitCode, stdOut or "")
    end,
    arguments
  )

  if not task then
    logOverviewTaskError(label, -1, "could not create task")
    callback(-1, "")
    return
  end

  table.insert(overviewTasks, task)

  if not task:start() then
    logOverviewTaskError(label, -1, "could not start task")
    callback(-1, "")
  end
end

local function loadOverviewData(state)
  startOverviewTask(
    state,
    "workspace list",
    { "list-workspaces", "--all" },
    function(exitCode, output)
      state.workspaceListFinished = true

      if exitCode == 0 then
        for _, workspace in ipairs(parseWorkspaceNames(output)) do
          state.workspaces[workspace] =
            state.workspaces[workspace] or {}
        end
      end

      logOverviewTiming(state, "workspace list ready")
      renderOverview(state)
    end
  )

  startOverviewTask(
    state,
    "focused workspace",
    { "list-workspaces", "--focused" },
    function(exitCode, output)
      state.focusedWorkspaceFinished = true

      if exitCode == 0 then
        state.focusedWorkspace = trim(output)
      end

      logOverviewTiming(state, "focused workspace ready")
      renderOverview(state)
    end
  )

  startOverviewTask(
    state,
    "window list",
    {
      "list-windows",
      "--all",
      "--format",
      "%{workspace}\t%{app-name}\t%{window-title}"
    },
    function(exitCode, output)
      state.windowsFinished = true

      if exitCode == 0 then
        -- Once window discovery finishes, keep only workspaces that actually
        -- contain windows. The earlier workspace-list result is provisional.
        state.workspaces = parseWindows(output)
      end

      logOverviewTiming(state, "window list ready")
      renderOverview(state)
    end
  )
end

local function showOverview()
  local startedAt = hs.timer.absoluteTime()

  if overview then
    hideOverview()
    return
  end

  local screen = hs.mouse.getCurrentScreen()
  local frame = screen:frame()

  overviewRequestId = overviewRequestId + 1

  local state = {
    requestId = overviewRequestId,
    startedAt = startedAt,
    frame = frame,
    workspaces = {},
    focusedWorkspace = "",
    workspaceListFinished = false,
    focusedWorkspaceFinished = false,
    windowsFinished = false,
    finalRenderQueued = false,
    navigationTimings = {}
  }

  local width, height, columns =
    calculateOverviewSize(state.workspaces, frame)

  local x = frame.x + (frame.w - width) / 2
  local y = frame.y + (frame.h - height) / 2

  local html = buildHTML(
    state.workspaces,
    state.focusedWorkspace,
    columns,
    true,
    true
  )

  overview = hs.webview.new({
    x = x,
    y = y,
    w = width,
    h = height
  })

  overview
    :windowStyle({ "borderless", "nonactivating" })
    :level(hs.drawing.windowLevels.popUpMenu)
    :behaviorAsLabels({
      "canJoinAllSpaces",
      "fullScreenAuxiliary"
    })
    :transparent(true)
    :allowTextEntry(false)
    :deleteOnClose(true)

  overview:navigationCallback(function(action, webview, navigationId)
    if not overviewIsCurrent(state) then
      return
    end

    if action == "didFinishNavigation" then
      local timingLabel = state.navigationTimings[navigationId]

      if timingLabel then
        state.navigationTimings[navigationId] = nil
        logOverviewTiming(state, timingLabel)
      end
    end
  end)

  overview:policyCallback(function(action, webview, info)
    if action ~= "navigationAction" then
      return true
    end

    local request = info.request
    if not request or not request.URL then
      return true
    end

    local url = request.URL

    local ws = url:match("^aerospace://workspace/(.+)$")

    if ws then
      switchToWorkspace(ws)

      return false
    end

    return true
  end)

  escapeHotkey = hs.hotkey.new({}, "escape", function()
    hideOverview()
  end)
  
  escapeHotkey:enable()

  setOverviewContent(state, html, "loading view rendered")

  overview:show()
  overview:bringToFront(true)

  logOverviewTiming(state, "webview show requested")

  -- Give WebKit a turn to display the loading view before starting processes.
  hs.timer.doAfter(0, function()
    if overviewIsCurrent(state) then
      loadOverviewData(state)
    end
  end)
end

------------------------------------------------------------
-- HOTKEY
------------------------------------------------------------

hs.hotkey.bind({ "alt" }, "o", showOverview)

------------------------------------------------------------
-- Optional: reload config quickly with Alt+Shift+Ctrl+Cmd+R
------------------------------------------------------------

hs.hotkey.bind(
  { "alt", "shift", "ctrl", "cmd" },
  "r",
  hs.reload
)

hs.alert.show("Hammerspoon config loaded")
