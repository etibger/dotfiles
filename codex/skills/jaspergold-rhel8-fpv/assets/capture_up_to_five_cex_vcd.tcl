# FTRun wrapper for a GPU Formal Jasper target.
#
# Required environment variable:
#   FTRUN_BASE_TCL    Ordinary target Tcl that this -tcl wrapper replaces.
# Optional environment variables:
#   FTRUN_RUN_LIMIT  Active proof limit, for example 10m or 2h.
#   FTRUN_PROVE_TASK FTS task that proves the properties (default prj_prove_all).
#   FTRUN_CEX_PROPERTY_GLOB Tcl glob selecting a preferred failed property.
#
# The wrapper preserves the target's ordinary termination behavior, saves at
# most five raw VCDs, then creates one synchronous QuietTrace VCD from the
# first failing Jasper property during the normal final hook. FTS
# runtime.failure_limit counts failed tasks, not individual property CEXs, so
# this wrapper deliberately does not claim or configure a five-property stop.

if {![info exists ::env(FTRUN_BASE_TCL)] ||
    $::env(FTRUN_BASE_TCL) eq ""} {
  error "Set FTRUN_BASE_TCL to the target's ordinary Tcl before ftrun"
}

source $::env(FTRUN_BASE_TCL)

namespace eval ::LOCAL_FPV_CEX {}

if {[info exists ::env(FTRUN_PROVE_TASK)] &&
    $::env(FTRUN_PROVE_TASK) ne ""} {
  set ::LOCAL_FPV_CEX::prove_task $::env(FTRUN_PROVE_TASK)
} else {
  set ::LOCAL_FPV_CEX::prove_task prj_prove_all
}

# Apply overrides before the common pre_configure hook checks the total runtime.
rename ::fts::hook::pre_configure ::LOCAL_FPV_CEX::base_pre_configure
proc ::fts::hook::pre_configure {} {
  variable ::LOCAL_FPV_CEX::prove_task

  if {![info exists ::env(FPV_MAX_JOBS)] ||
      ![string is integer -strict $::env(FPV_MAX_JOBS)] ||
      $::env(FPV_MAX_JOBS) < 1} {
    error "FPV_MAX_JOBS must be a positive integer"
  }
  set jobs $::env(FPV_MAX_JOBS)
  set per_engine_jobs [expr {$jobs < 2 ? $jobs : 2}]
  set strategy [::fts::cfg_get runtime tasks $prove_task prove_strategy]
  if {$strategy eq ""} {
    error "No prove strategy configured for $prove_task"
  }

  # Preserve the documented FTS controls as resolved configuration evidence.
  # Jasper ProofMaster can replace the generic proof-grid settings later, so
  # ::fts::hook::main also applies the Jasper-local limits immediately before
  # FTS auto_run starts the proof.
  ::fts::cfg_set [list runtime prove_strategies $strategy max_jobs] $jobs
  ::fts::cfg_set \
    [list runtime prove_strategies $strategy per_engine_max_jobs] \
    $per_engine_jobs
  ::fts::cfg_set {tool_config jg per_engine_max_jobs} $per_engine_jobs

  if {[info exists ::env(FTRUN_RUN_LIMIT)] &&
      $::env(FTRUN_RUN_LIMIT) ne ""} {
    set run_limit $::env(FTRUN_RUN_LIMIT)
    ::fts::cfg_set {tool_config jg run_limit} $run_limit

    ::fts::cfg_set \
      [list runtime prove_strategies $strategy run_limit] $run_limit
  }

  ::fts::cfg_set [list runtime tasks $prove_task fail_on] cex

  # Keep an automatically generated raw trace if QuietTrace generation fails.
  ::fts::cfg_set {report save_cex format} vcd
  ::fts::cfg_set {report save_cex limit} 5
  ::fts::cfg_set {report save_cex source} tool

  ::LOCAL_FPV_CEX::base_pre_configure
}

# This documented FTS hook runs after normal tool/engine configuration and
# before auto_run.  Generic set_proofgrid_max_jobs settings are not sufficient
# for a local ProofMaster run: orchestration can replace them with "auto".
# These Jasper-local settings remain the effective total and per-engine caps.
rename ::fts::hook::main ::LOCAL_FPV_CEX::base_main
proc ::fts::hook::main {} {
  ::LOCAL_FPV_CEX::base_main

  if {$::fts::TOOL ne "jg"} {
    return
  }

  set jobs $::env(FPV_MAX_JOBS)
  set per_engine_jobs [expr {$jobs < 2 ? $jobs : 2}]
  ::fts::tool_eval \
    ::set_proofgrid_per_engine_max_local_jobs $per_engine_jobs
  ::fts::tool_eval ::set_proofgrid_max_local_jobs $jobs
  puts "LOCAL_FPV_CONCURRENCY: max_local_jobs=$jobs per_engine_max_local_jobs=$per_engine_jobs"
}

proc ::LOCAL_FPV_CEX::save_first_cex {} {
  set cex_props [lsort [::fts::tool_eval get_property_list \
    -include {status {cex ar_cex} disabled 0}]]

  if {[llength $cex_props] == 0} {
    puts "LOCAL_FPV_CEX: no counterexample to save"
    return
  }

  set prop [lindex $cex_props 0]
  if {[info exists ::env(FTRUN_CEX_PROPERTY_GLOB)] &&
      $::env(FTRUN_CEX_PROPERTY_GLOB) ne ""} {
    set preferred {}
    foreach candidate $cex_props {
      if {[string match $::env(FTRUN_CEX_PROPERTY_GLOB) $candidate]} {
        lappend preferred $candidate
      }
    }
    if {[llength $preferred] == 0} {
      error "No failed property matched FTRUN_CEX_PROPERTY_GLOB=$::env(FTRUN_CEX_PROPERTY_GLOB)"
    }
    set prop [lindex $preferred 0]
  }
  set prop_leaf [lindex [split $prop .] end]
  set prop_leaf [regsub -all {[^[:alnum:]_-]} $prop_leaf _]
  set window local_fpv_first_cex
  set project_dir [string trim [::fts::tool_eval get_proj_dir]]
  set vcd_root [file join $project_dir "quiet_cex_${prop_leaf}"]

  puts "LOCAL_FPV_CEX: creating QuietTrace for $prop"
  ::fts::tool_eval visualize -violation -property $prop \
    -window $window -batch -silent
  ::fts::tool_eval visualize -replot -quiet \
    -window $window -batch -silent
  ::fts::tool_eval visualize -save -vcd $vcd_root \
    -window $window -force
  puts "LOCAL_FPV_CEX: saved $vcd_root.vcd"
}

# Preserve standard reporting and JDB save, then add the QuietTrace artifact.
rename ::PROJECT::hook::final ::LOCAL_FPV_CEX::base_final
proc ::PROJECT::hook::final {} {
  ::LOCAL_FPV_CEX::base_final

  if {$::fts::TOOL ne "jg"} {
    return
  }

  if {[catch {::LOCAL_FPV_CEX::save_first_cex} message options]} {
    puts stderr "LOCAL_FPV_CEX: QuietTrace VCD export failed: $message"
    puts stderr [dict get $options -errorinfo]
  }
}
