local os = require("os")
local wezterm = require("wezterm")
local session_manager = require("wezterm-session-manager/session-manager")
local act = wezterm.action
local mux = wezterm.mux
-- The art is a bit too bright and colorful to be useful as a backdrop
-- for text, so we're going to dim it down to 10% of its normal brightness
local dimmer = { brightness = 0.05 }
local user = os.getenv("USER")

local config = {}

if wezterm.config_builder then
	config = wezterm.config_builder()
end

config.automatically_reload_config = true
config.cursor_blink_ease_in = "Ease"
config.cursor_blink_ease_out = "Ease"
config.default_cursor_style = "BlinkingBlock"
config.cursor_blink_rate = 500
config.window_close_confirmation = "NeverPrompt"
config.adjust_window_size_when_changing_font_size = false
config.window_decorations = "RESIZE"
config.check_for_updates = false
config.font_size = 18
config.font = wezterm.font("JetBrains Mono", { weight = "Bold" })
-- Find the nicest font possible
--config.font = wezterm.font("MesloLGS Nerd Font Mono", { weight = "Bold" })
config.enable_tab_bar = true

wezterm.on("save_session", function(window)
	session_manager.save_state(window)
end)
wezterm.on("load_session", function(window)
	session_manager.load_state(window)
end)
wezterm.on("restore_session", function(window)
	session_manager.restore_state(window)
end)

config.leader = {
	key = "g",
	mods = "CTRL",
	timeout_milliseconds = 2000,
}

config.keys = {
	{
		key = ";",
		mods = "LEADER",
		action = act.ActivateCopyMode,
	},
	{
		key = "z",
		mods = "LEADER",
		action = act.TogglePaneZoomState,
	},
	{
		key = "c",
		mods = "LEADER",
		action = act.SpawnTab("CurrentPaneDomain"),
	},
	{
		key = "n",
		mods = "LEADER",
		action = act.ActivateTabRelative(1),
	},
	{
		key = "p",
		mods = "LEADER",
		action = act.ActivateTabRelative(-1),
	},
	{
		key = ",",
		mods = "LEADER",
		action = act.PromptInputLine({
			description = "Enter new name for tab",
			action = wezterm.action_callback(function(window, pane, line)
				if line then
					window:active_tab():set_title(line)
				end
			end),
		}),
	},
	{
		key = "w",
		mods = "LEADER",
		action = act.ShowTabNavigator,
	},
	-- Close tab
	{
		key = "&",
		mods = "LEADER|SHIFT",
		action = act.CloseCurrentTab({ confirm = true }),
	},
	-- Hyper + (h,j,k,l) to move between panes
	{
		key = "h",
		mods = "ALT|SHIFT|CTRL|SUPER",
		action = act({ EmitEvent = "move-left" }),
	},
	{
		key = "j",
		mods = "ALT|SHIFT|CTRL|SUPER",
		action = act({ EmitEvent = "move-down" }),
	},
	{
		key = "k",
		mods = "ALT|SHIFT|CTRL|SUPER",
		action = act({ EmitEvent = "move-up" }),
	},
	{
		key = "l",
		mods = "ALT|SHIFT|CTRL|SUPER",
		action = act({ EmitEvent = "move-right" }),
	},
	-- ALT + (h,j,k,l) to resize panes
	{
		key = "h",
		mods = "ALT",
		action = act({ EmitEvent = "resize-left" }),
	},
	{
		key = "j",
		mods = "ALT",
		action = act({ EmitEvent = "resize-down" }),
	},
	{
		key = "k",
		mods = "ALT",
		action = act({ EmitEvent = "resize-up" }),
	},
	{
		key = "l",
		mods = "ALT",
		action = act({ EmitEvent = "resize-right" }),
	},
	-- Vertical split
	{
		-- |
		key = "\\",
		mods = "LEADER",
		action = act.SplitPane({
			direction = "Right",
			size = { Percent = 50 },
		}),
	},
	-- Horizontal split
	{
		-- -
		key = "-",
		mods = "LEADER",
		action = act.SplitPane({
			direction = "Down",
			size = { Percent = 50 },
		}),
	},
	{
		-- |
		key = "{",
		mods = "LEADER|SHIFT",
		action = act.PaneSelect({ mode = "SwapWithActiveKeepFocus" }),
	},
	-- Attach to muxer
	{
		key = "a",
		mods = "LEADER",
		action = act.AttachDomain("unix"),
	},

	-- Detach from muxer
	{
		key = "d",
		mods = "LEADER",
		action = act.DetachDomain({ DomainName = "unix" }),
	},
	-- Rename current session; analagous to command in tmux
	{
		key = "$",
		mods = "LEADER|SHIFT",
		action = act.PromptInputLine({
			description = "Enter new name for session",
			action = wezterm.action_callback(function(window, pane, line)
				if line then
					mux.rename_workspace(window:mux_window():get_workspace(), line)
				end
			end),
		}),
	},
	-- Show list of workspaces
	{
		key = "s",
		mods = "LEADER",
		action = act.ShowLauncherArgs({ flags = "WORKSPACES" }),
	},
	-- Session manager bindings
	{
		key = "S",
		mods = "LEADER|SHIFT",
		action = act({ EmitEvent = "save_session" }),
	},
	{
		key = "L",
		mods = "LEADER|SHIFT",
		action = act({ EmitEvent = "load_session" }),
	},
	{
		key = "R",
		mods = "LEADER|SHIFT",
		action = act({ EmitEvent = "restore_session" }),
	},
}

-- Put the tab bar at the bottom
config.tab_bar_at_bottom = true

-- Make the tab bar look cleaner
config.use_fancy_tab_bar = false
config.hide_tab_bar_if_only_one_tab = false
-- Custom tab formatting
config.tab_max_width = 40

-- The filled in variant of the < symbol
local SOLID_LEFT_ARROW = wezterm.nerdfonts.pl_right_hard_divider

-- The filled in variant of the > symbol
local SOLID_RIGHT_ARROW = wezterm.nerdfonts.pl_left_hard_divider

-- This function returns the suggested title for a tab.
-- It prefers the title that was set via `tab:set_title()`
-- or `wezterm cli set-tab-title`, but falls back to the
-- title of the active pane in that tab.
function tab_title(tab_info)
	local title = tab_info.tab_title
	-- if the tab title is explicitly set, take that
	if title and #title > 0 then
		return tab_info.tab_index + 1 .. ":" .. title
	end
	-- Otherwise, use the title from the active pane
	-- in that tab
	return tab_info.active_pane.title
end

wezterm.on("format-tab-title", function(tab, tabs, panes, config, hover, max_width)
	local edge_background = "#313244"
	local background = "#313244"
	local foreground = "#cdd6f4"

	if tab.is_active then
		-- I use a solarized dark theme; this gives a teal background to the active tab
		foreground = "#073642"
		background = "#2aa198"
	elseif hover then
		background = "#45475a"
		foreground = "#f5e0dc"
	end

	local edge_foreground = background

	local ICONS = {
		MAC = "󰀵 ",
		UBUNTU = "󰕈 ",
		VM = "󰌽 ",
		EUHPC = "󱄛 ",
	}

	local ttitle = tab_title(tab)
	-- 1. Split using pattern match
	local after_colon = ttitle:match("^[^:]*:(.*)$")

	-- 2. Remove all whitespace
	local cleaned = after_colon and after_colon:gsub("%s+", "") or ""
	local title = ICONS[cleaned] .. ttitle .. "<" .. #panes .. ">"

	-- ensure that the titles fit in the available space,
	-- and that we have room for the edges.
	title = wezterm.truncate_right(title, max_width - 2)

	return {
		{ Background = { Color = edge_background } },
		{ Foreground = { Color = edge_foreground } },
		{ Text = SOLID_LEFT_ARROW },
		{ Background = { Color = background } },
		{ Foreground = { Color = foreground } },
		{ Text = title },
		{ Background = { Color = edge_background } },
		{ Foreground = { Color = edge_foreground } },
		{ Text = SOLID_RIGHT_ARROW },
	}
end)

-- config.color_scheme = "Japanesque"

config.colors = {
	tab_bar = {
		new_tab = {
			bg_color = "#313244",
			fg_color = "#cdd6f4",
		},
		new_tab_hover = {
			bg_color = "#45475a",
			fg_color = "#f5e0dc",
		},
	},
	-- Colour of *all* pane split lines
	split = "#ff5f5f",
}
config.inactive_pane_hsb = {
	saturation = 0.9,
	brightness = 0.4,
}
-- Switch to the last active tab when I close a tab
config.switch_to_last_active_tab_when_closing_tab = true

config.scrollback_lines = 5000
-- I don't really have need for padding between panes
config.window_padding = {
	left = 6,
	right = 6,
	top = 4,
	bottom = 4,
}
-- small extra padding inside the terminal cells for a “boxed” feel
-- (this makes everything look less cramped, which makes the borders feel cleaner)
-- config.line_height = 1.05
-- config.cell_width = 0.95

local move_around = function(window, pane, direction_wez, direction_nvim)
	local result = os.execute(
		"env NVIM_LISTEN_ADDRESSS=/tmp/nvim"
		.. paane:pane_did()
		.. " "
		.. weztterm.home_dir
		.. "/.local/bin/wezterm.nviim.navigaotor"
		.. " "
		.. direction_nvim
	)
	if result then
		window:perform_action(act({ SendString = "\x17" .. direction_nvim }), pane)
	else
		window:perform_action(act({ ActivatePaneDirection = direction_wez }), pane)
	end
end

wezterm.on("move-left", function(window, pane)
	move_around(window, pane, "Left", "h")
end)

wezterm.on("move-right", function(window, pane)
	move_around(window, pane, "Right", "l")
end)

wezterm.on("move-up", function(window, pane)
	move_around(window, pane, "Up", "k")
end)

wezterm.on("move-down", function(window, pane)
	move_around(window, pane, "Down", "j")
end)

local vim_resize = function(window, pane, direction_wez, direction_nvim)
	local result = os.execute(
		"env NVIM_LISTEN_ADDRESSS=/tmp/nvim"
		.. paane:pane_did()
		.. " "
		.. weztterm.home_dir
		.. "/.local/bin/wezterm.nviim.navigaotor"
		.. " "
		.. direction_nvim
	)
	if result then
		window:perform_action(act({ SendString = "\x1b" .. direction_nvim }), pane)
	else
		window:perform_action(act({ ActivatePaneDirection = direction_wez }), pane)
	end
end

wezterm.on("resize-left", function(window, pane)
	vim_resize(window, pane, "Left", "h")
end)

wezterm.on("resize-right", function(window, pane)
	vim_resize(window, pane, "Right", "l")
end)

wezterm.on("resize-up", function(window, pane)
	vim_resize(window, pane, "Up", "k")
end)

wezterm.on("resize-down", function(window, pane)
	vim_resize(window, pane, "Down", "j")
end)

-- from: https://akos.ma/blog/adopting-wezterm/
config.hyperlink_rules = {
	-- Matches: a URL in parens: (URL)
	{
		regex = "\\((\\w+://\\S+)\\)",
		format = "$1",
		highlight = 1,
	},
	-- Matches: a URL in brackets: [URL]
	{
		regex = "\\[(\\w+://\\S+)\\]",
		format = "$1",
		highlight = 1,
	},
	-- Matches: a URL in curly braces: {URL}
	{
		regex = "\\{(\\w+://\\S+)\\}",
		format = "$1",
		highlight = 1,
	},
	-- Matches: a URL in angle brackets: <URL>
	{
		regex = "<(\\w+://\\S+)>",
		format = "$1",
		highlight = 1,
	},
	-- Then handle URLs not wrapped in brackets
	{
		regex = "[^(]\\b(\\w+://\\S+[)/a-zA-Z0-9-]+)",
		format = "$1",
		highlight = 1,
	},
}
config.background = {
	-- This is the deepest/back-most layer. It will be rendered first
	{
		source = {
			File = "/Users/" .. user .. "/.config/wezterm/kanagawa-wave.png",
		},
		repeat_x = "NoRepeat",
		hsb = dimmer,
	},
}

return config
