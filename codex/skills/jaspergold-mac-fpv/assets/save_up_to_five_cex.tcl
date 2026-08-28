# FTRun wrapper for the Wave A Mac fb_tex_flt detector.
#
# Required environment:
#   FTRUN_BASE_TCL   Normal target Tcl replaced by this wrapper.
#   FTRUN_RUN_LIMIT Active proof limit, fixed to 10m by the executor.
# Optional:
#   FTRUN_PROVE_TASK Task using the prove strategy (default prj_prove_all).
#
# This wrapper bounds automatic raw CEX trace saving at five. It deliberately
# does not claim to stop proof after five assertion CEXes. A live run proved
# runtime.failure_limit=5 is not an individual-property counter for this
# single FTS task. Stop-after-five needs a tested property monitor/cancellation
# implementation before it can be enabled.

if {![info exists ::env(FTRUN_BASE_TCL)] ||
    $::env(FTRUN_BASE_TCL) eq ""} {
  error "Set FTRUN_BASE_TCL to the target's ordinary Tcl before ftrun"
}

source $::env(FTRUN_BASE_TCL)

namespace eval ::WAVE_A_FPV {}

if {[info exists ::env(FTRUN_PROVE_TASK)] &&
    $::env(FTRUN_PROVE_TASK) ne ""} {
  set ::WAVE_A_FPV::prove_task $::env(FTRUN_PROVE_TASK)
} else {
  set ::WAVE_A_FPV::prove_task prj_prove_all
}

rename ::fts::hook::pre_configure ::WAVE_A_FPV::base_pre_configure
proc ::fts::hook::pre_configure {} {
  variable ::WAVE_A_FPV::prove_task

  # Let the standard project hook establish its configuration first, then
  # apply the campaign bounds so they cannot be overwritten by that hook.
  ::WAVE_A_FPV::base_pre_configure

  if {[info exists ::env(FTRUN_RUN_LIMIT)] &&
      $::env(FTRUN_RUN_LIMIT) ne ""} {
    set run_limit $::env(FTRUN_RUN_LIMIT)
    ::fts::cfg_set {tool_config jg run_limit} $run_limit
    set strategy [::fts::cfg_get runtime tasks $prove_task prove_strategy]
    if {$strategy ne ""} {
      ::fts::cfg_set \
        [list runtime prove_strategies $strategy run_limit] $run_limit
    }
  }

  ::fts::cfg_set {report save_cex format} vcd
  ::fts::cfg_set {report save_cex limit} 5
  ::fts::cfg_set {report save_cex source} tool
  puts "WAVE_A_FPV: raw CEX save limit=5; stop-after-five-CEX is not implemented"
}
