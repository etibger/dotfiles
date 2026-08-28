# Input is `ps -eo pid=,ppid=,state=,pcpu=,etimes=,comm=,args=`. Linux reports
# the real engine executable in comm (field 6), while argv[0] in args is
# jg_proof (field 7). Count run-scoped JG processes, and optionally retain the
# PID/parent/state/argv evidence needed to distinguish ordinary ProofGrid
# engines, ProofMaster prove-cache workers, and the main/controller or other
# JG helpers.  `comm` is authoritative for jg_engineCache: its argv also names
# a .proofgrid_*.bs file, so argv alone would misclassify it as a proof slot.
$7 == "jg_proof" && index($0, needle) {
  count++
  role = ($6 == "jg_engineCache") \
    ? "proof_cache_worker" \
    : (($0 ~ /\.proofgrid_[^ ]*\.bs([[:space:]]|$)/) \
      ? "ordinary_proof_engine" \
      : "controller_or_other")
  if (details_file != "") {
    printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t", \
      sample_epoch, $1, $2, $3, $4, $5, $6, role >> details_file
    for (field = 7; field <= NF; field++) {
      printf "%s%s", (field == 7 ? "" : " "), $field >> details_file
    }
    printf "\n" >> details_file
  }
}

END {
  print count + 0
}
