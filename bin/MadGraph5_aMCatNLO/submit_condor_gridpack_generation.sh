#!/bin/bash
source Utilities/source_condor.sh

name=$1
carddir=$2
workqueue="condor"
scram_arch=$3
cmssw_version=$4
# jobstep can be 'ALL','CODEGEN', 'INTEGRATE', 'MADSPIN'
jobstep=$7

if [ -n "$5" ]; then 
  # espresso     = 20 minutes
  # microcentury = 1 hour
  # longlunch    = 2 hours
  # workday      = 8 hours
  # tomorrow     = 1 day
  # testmatch    = 3 days
  # nextweek     = 1 week
  export CONDOR_JOB_FLAVOUR=$5
fi

if [ -n "$6" ]; then
  export CONDOR_DEBUG_OUTPUT_PATH=$6
  if [ ! -d "$6" ]; then
    echo $CONDOR_DEBUG_OUTPUT_PATH" directory doesn't exist, please create it before condor run"
    exit
  fi
fi

bash gridpack_generation.sh ${name} ${carddir} ${workqueue} ${jobstep} ${scram_arch} ${cmssw_version}
