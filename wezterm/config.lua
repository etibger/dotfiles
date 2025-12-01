local wezterm = require("wezterm")
local config = {}

if wezterm.config_builder then
	config = wezterm.config_builder()
end

config.automatically_reload_config = true
config.cursor_blink_ease_in = 'Ease'
config.cursor_blink_ease_out = 'Ease'
config.default_cursor_style = "BlinkingBlock"
config.cursor_blink_rate = 500
config.window_close_confirmation = "NeverPrompt"
config.adjust_window_size_when_changing_font_size = false
config.window_decorations = "RESIZE"
config.check_for_updates = false
config.use_fancy_tab_bar = false
config.tab_bar_at_bottom = true
config.font_size = 18
config.font = wezterm.font("JetBrains Mono", { weight = "Bold" })
-- Find the nicest font possible
--config.font = wezterm.font("MesloLGS Nerd Font Mono", { weight = "Bold" })
config.enable_tab_bar = true
config.window_padding = {
	left = 7,
	right = 0,
	top = 2,
	bottom = 0,
}

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
return config
