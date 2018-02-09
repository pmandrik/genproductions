
import madgraph.various.cluster as cluster
import madgraph.various.misc as misc
import subprocess, os, re

import logging

ClusterManagmentError = cluster.ClusterManagmentError
logger = logging.getLogger('madgraph.cluster') 

class LXPLUS_htcondor_cluster(cluster.CondorCluster):
    name = 'condor'
    job_id = 'CONDOR_ID'

    jobstatus = {'0':'U', '1':'I','2':'R','3':'X','4':'C','5':'H','6':'E'}
    @cluster.check_interupt()
    @cluster.multiple_try(nb_try=10, sleep=10)
    def control(self, me_dir):
        """ control the status of a single job with it's cluster id """
        
        if not self.submitted_ids:
            return 0, 0, 0, 0
        
        packet = 15000
        idle, run, fail = 0, 0, 0
        ongoing = []
        for i in range(1+(len(self.submitted_ids)-1)//packet):
            start = i * packet
            stop = (i+1) * packet
            cmd = "condor_q " + ' '.join(self.submitted_ids[start:stop]) + \
            " -format \"%d \"   ClusterId " + \
            " -format \"%d \"   ProcId " + \
            " -format \"%d\\n\"  JobStatus "

            status = misc.Popen([cmd], shell=True, stdout=subprocess.PIPE,
                                                             stderr=subprocess.PIPE)
            error = status.stderr.read()
            if status.returncode or error:
                raise ClusterManagmentError, 'condor_q returns error: %s' % error

            for line in status.stdout:
                cluster_id, proc_id, status = line.strip().split()
                status = self.jobstatus[status]
                ongoing.append(cluster_id)
                if status in ['I','U']:
                    idle += 1
                elif status == 'R':
                    run += 1
                elif status == 'C' :
                    p = subprocess.Popen(['condor_transfer_data', cluster_id + "." + proc_id], stdout=subprocess.PIPE)
                    p.wait()
                    if p.returncode != 0:
                        logger.warning("condor_transfer_data " + cluster_id + "." + proc_id + " failded to fetch the spooled data")
                    else : logger.info("condor_transfer_data " + cluster_id + "." + proc_id + " fetch the spooled data ok")
                elif status != 'C':
                    logger.warning("condor job " + cluster_id + "." + proc_id + " has a failed state " + status)
                    fail += 1

        for id in list(self.submitted_ids):
            if id not in ongoing:
                status = self.check_termination(id)
                if status == 'wait':
                    run += 1
                elif status == 'resubmit':
                    idle += 1

        return idle, run, self.submitted - (idle+run+fail), fail

    @cluster.multiple_try()
    def submit(self, prog, argument=[], cwd=None, stdout=None, stderr=None, log=None,
               required_output=[], nb_submit=0):
        """Submit a job prog to a Condor cluster"""
        
        text = """Executable = %(prog)s
                  output = %(stdout)s
                  error = %(stderr)s
                  log = %(log)s
                  %(argument)s
                  environment = CONDOR_ID=$(Cluster).$(Process)
                  Universe = vanilla
                  notification = Error
                  Initialdir = %(cwd)s
                  %(requirement)s
                  getenv=True
                 +JobFlavour = "%(job_flavour)s"
                  leave_in_queue = (JobStatus == 4) && ((StageOutFinish =?= UNDEFINED) || (StageOutFinish == 0))
                  queue 1
                """
        
        if self.cluster_queue not in ['None', None]:
            requirement = 'Requirements = %s=?=True' % self.cluster_queue
        else:
            requirement = ''

        if cwd is None:
            cwd = os.getcwd()
        if stdout is None:
            stdout = '/dev/null'
        if stderr is None:
            stderr = '/dev/null'
        if log is None:
            log = '/dev/null'
        if not os.path.exists(prog):
            prog = os.path.join(cwd, prog)
        if argument:
            argument = 'Arguments = %s' % ' '.join(argument)
        else:
            argument = ''

        # keep condor logs if CONDOR_DEBUG_OUTPUT_PATH variable is defined
        debug_output_path = os.environ.get("CONDOR_DEBUG_OUTPUT_PATH", "")
        if debug_output_path : 
          stdout = os.path.normpath(debug_output_path) + "/" + "job_$(ClusterId)_$(JobId)_stdout.txt"
          stderr = os.path.normpath(debug_output_path) + "/" + "job_$(ClusterId)_$(JobId)_stderr.txt"
          log    = os.path.normpath(debug_output_path) + "/" + "job_$(ClusterId)_$(JobId)_condor.txt"

        # set job maximum execution time
        job_flavour = os.environ.get("CONDOR_JOB_FLAVOUR", "tomorrow")
 
        dico = {'prog': prog, 'cwd': cwd, 'stdout': stdout, 
                 'stderr': stderr,'log': log,'argument': argument,
                'requirement': requirement, 'job_flavour' : job_flavour}
 
         #open('submit_condor','w').write(text % dico)

        a = misc.Popen(['condor_submit', '-spool'], stdout=subprocess.PIPE,
                       stdin=subprocess.PIPE)
        output, _ = a.communicate(text % dico)
        #output = a.stdout.read()
        #Submitting job(s).
        #Logging submit event(s).
        #1 job(s) submitted to cluster 2253622.
        pat = re.compile("submitted to cluster (\d*)",re.MULTILINE)
        try:
            id = pat.search(output).groups()[0]
        except:
            raise ClusterManagmentError, 'fail to submit to the cluster: \n%s' \
                                                                        % output 
        self.submitted += 1
        self.submitted_ids.append(id)
        return id

    @cluster.store_input()
    @cluster.multiple_try()
    def submit2(self, prog, argument=[], cwd=None, stdout=None, stderr=None, 
                log=None, input_files=[], output_files=[], required_output=[], 
                nb_submit=0):
        """Submit the job on the cluster NO SHARE DISK
           input/output file should be give relative to cwd
        """
        
        if not required_output and output_files:
            required_output = output_files
        
        if (input_files == [] == output_files):
            return self.submit(prog, argument, cwd, stdout, stderr, log, 
                               required_output=required_output, nb_submit=nb_submit)
        
        text = """Executable = %(prog)s
                  output = %(stdout)s
                  error = %(stderr)s
                  log = %(log)s
                  %(argument)s
                  should_transfer_files = YES
                  when_to_transfer_output = ON_EXIT
                  transfer_input_files = %(input_files)s
                  %(output_files)s
                  Universe = vanilla
                  notification = Error
                  Initialdir = %(cwd)s
                  %(requirement)s
                  +JobFlavour = "%(job_flavour)s"
                  leave_in_queue = (JobStatus == 4) && ((StageOutFinish =?= UNDEFINED) || (StageOutFinish == 0))
                  getenv=True
                  queue 1
               """
        
        if self.cluster_queue not in ['None', None]:
            requirement = 'Requirements = %s=?=True' % self.cluster_queue
        else:
            requirement = ''

        if cwd is None:
            cwd = os.getcwd()
        if stdout is None:
            stdout = '/dev/null'
        if stderr is None:
            stderr = '/dev/null'
        if log is None:
            log = '/dev/null'
        if not os.path.exists(prog):
            prog = os.path.join(cwd, prog)
        if argument:
            argument = 'Arguments = %s' % ' '.join([str(a) for a in argument])
        else:
            argument = ''
        # input/output file treatment
        if input_files:
            input_files = ','.join(input_files)
        else: 
            input_files = ''
        if output_files:
            output_files = 'transfer_output_files = %s' % ','.join(output_files)
        else:
            output_files = ''
        
        # keep condor logs if CONDOR_DEBUG_OUTPUT_PATH variable is defined
        debug_output_path = os.environ.get("CONDOR_DEBUG_OUTPUT_PATH", "")
        if debug_output_path : 
          stdout = os.path.normpath(debug_output_path) + "/" + "job_$(ClusterId)_$(JobId)_stdout.txt"
          stderr = os.path.normpath(debug_output_path) + "/" + "job_$(ClusterId)_$(JobId)_stderr.txt"
          log    = os.path.normpath(debug_output_path) + "/" + "job_$(ClusterId)_$(JobId)_condor.txt"

        # set job maximum execution time
        job_flavour = os.environ.get("CONDOR_JOB_FLAVOUR", "tomorrow")


        dico = {'prog': prog, 'cwd': cwd, 'stdout': stdout, 
                'stderr': stderr,'log': log,'argument': argument,
                'requirement': requirement, 'input_files':input_files, 
                'output_files':output_files, 'job_flavour' : job_flavour}

        #open('submit_condor','w').write(text % dico)
        a = subprocess.Popen(['condor_submit', '-spool'], stdout=subprocess.PIPE,
                             stdin=subprocess.PIPE)
        output, _ = a.communicate(text % dico)
        #output = a.stdout.read()
        #Submitting job(s).
        #Logging submit event(s).
        #1 job(s) submitted to cluster 2253622.
        pat = re.compile("submitted to cluster (\d*)",re.MULTILINE)
        try:
            id = pat.search(output).groups()[0]
        except:
            raise ClusterManagmentError, 'fail to submit to the cluster: \n%s' \
                                                                        % output 
        self.submitted += 1
        self.submitted_ids.append(id)
        return id




