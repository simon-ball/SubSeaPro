# -*- coding: utf-8 -*-
"""
Created on Fri May 31 13:50:33 2019

@author: simoba
"""
# celery -A proj worker -l info
import sys
import os
import time
import shlex
import shutil
import random
import zipfile
import subprocess
from pathlib import Path
from celery import Celery
from datetime import datetime

import ssp.server_config as config
import ssp.server_secrets as secrets

#app = Celery("server_main", broker="pyamqp://user:password@ipaddress//")
# Configure the queue that keeps track of jobs still to be completed
fn = os.path.basename(sys.argv[0]).split('.')[0] # Name of this script
queue = Celery(fn, broker="pyamqp://%s:%s@%s//" % (secrets.quser, secrets.qpwd, secrets.host))

@queue.task
def task(task_id):
    '''complete a Task:
        * Extract all jobs that are part of the task
        * Calculate each job in turn
        * Tidy uo at the end
    '''
    os.makedirs(config.root_finished / task_id, exist_ok=True)
    os.makedirs(config.root_failed / task_id, exist_ok=True)
    task_dir = config.root_job / task_id
    archive = task_dir / (task_id+".zip")
    ids = []
    print("Extracting all jobs in '%s'" % task_id)
    with zipfile.ZipFile(archive, "r") as cfile:
        for f in cfile.namelist():
            job_id = f.split(os.sep)[0]
            if job_id not in ids:
                ids.append(job_id)
                cfile.extract(f, task_dir)
    print("Beginning calculations in '%s'" % task_id)
    for job_id in ids:
        job_start = time.time()
        print("Beginning job '%s'" % job_id)
        '''Actual job begins here'''
            # Call Ampl
        # TODO: need to further investigate correctly escaping the identifier, since it's user-entered input
        # possibly shlex.quote() ?
    #    done = subprocess.run([config.bash_command, run_file], shell=True, 
    #                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE) 
        run_file = task_dir / job_id / config.file_in
        print(run_file)
        time.sleep(2)
        a = random.random()
        success = False
        if a < 0.8:
            success = True
        '''Actual job ends here'''
        job_stop = time.time()
        duration = job_stop - job_start
        _write_task_progress(task_id, job_id, ids, duration)
    #    if done.returncode == 0:
    #        success = True
    #    else:
    #        success = False
    #    if success:
    #        # Move the results to the output folder
    #        pass
    #    else:
    #        # Move the job to the failed folder
    #        pass
        #https://docs.python.org/3/library/subprocess.html
        # Use this for switching between success of failure?
        _move_ended_job(task_id, job_id, success)
    print("task '%s' finished" % task_id)
    _task_cleanup(task_id)
    pass
@queue.task
def test(task_id, job_id):
    print("starting %s, %s" % (task_id, job_id))
    time.sleep(2)
    print("stopping %s, %s" % (task_id, job_id))
    return True

  
###############################################################################
###################             HELPER FUNCTIONS
###############################################################################   


def _move_ended_job(task_id, job_id, succeeded):
    '''For a job that has ended, move to the relevant location and update the 
    relevant list. Relevancy is determined by whether the job finished 
    successfully, or failed with some error
    '''
    old_dir = Path(config.root_job, task_id, job_id)
    if succeeded:
        print("Moving successful job to /finished")
        new_dir = str(Path(config.root_finished, task_id))
        record = config.list_finished
    else:
        print("Moving unsuccessful job to /failed")
        new_dir = str(Path(config.root_failed, task_id))
        record = config.list_failed
    os.makedirs(new_dir, exist_ok=True)
    shutil.move(str(old_dir), str(new_dir))
    with open(record, "a+") as f:
        f.write(str(Path(task_id, job_id)))
        f.write("\n")
    
def _check_if_task_finished(task_id, job_id):
    '''Test whether all jobs assigned to a single task are completed.
    
    Evaluate the total number of jobs from the original task archive. If the 
    number of finished+failed jobs is equal to this, then the task is complete
    If there are job folders remaining that are not the current job, then that
    job must have crashed in some way - re-add it
    '''
    task_dir = config.root_job / task_id
    archive = task_dir / (task_id+".zip")
    with zipfile.ZipFile(archive, "r") as cfile:
        contents = cfile.namelist()
    jobs = []
    for line in contents:
        job_id = line.split(os.path.sep)[0]
        if job_id not in jobs:
            jobs.append(job_id)
    num_jobs = len(jobs)
    
    # Check the number of finished, failed jobs
    num_finished = len(os.listdir(config.root_finished / task_id))
    num_failed = len(os.listdir(config.root_failed / task_id))
    hanging = os.listdir(config.root_job / task_id)
    for name in hanging:
        if name == job_id or not os.path.isdir(name):
            hanging.remove(name)
    if num_finished + num_failed == num_jobs:
        finished = True
    else:
        finished = False
    return finished
        
def _task_cleanup(task_id):
    '''At the end of a task, tidy things up and prepare the task for download'''
    # Gather all the relevant files into a single zip file for download
    # The zip structure will contain a structure like:
    # task1.zip
    #   finished
    #       job1
    #       job2
    #   failed
    #       job3
    
    # move jobs into correct structure
    subprocess.run('mkdir -p "%s"' % _sanitise(config.root_download / task_id), shell=True)
    new_fin_dir = str(config.root_download / task_id / config.finished)
    new_fail_dir = str(config.root_download / task_id / config.failed)
    shutil.move(str(config.root_finished / task_id), new_fin_dir)
    shutil.move(str(config.root_failed / task_id), new_fail_dir)
    
    # zip into archive
    archive_name = config.root_download / (task_id + config.complete)
    with zipfile.ZipFile(archive_name, "a") as archive:
        for location in (new_fin_dir, new_fail_dir):
            for root, dirs, files in os.walk(location):
                for file in files:
                    archive.write(os.path.join(root, file))
    # Delete folders
    shutil.rmtree(str(config.root_download / task_id))
    shutil.rmtree(str(config.root_job / task_id))
    progress_file = config.root_job / (task_id+config.progress)
    os.remove(str(progress_file))
    return True
    

def _sanitise(text):
    '''Use the shlex library to safely escape **most** dangerous inputs before 
    calling them at the commandline'''
    return shlex.quote(str(text))



def _write_task_progress(task_id, job_id, all_ids, duration):
    record = config.root_job / (task_id+config.progress)
    progress = (1 + all_ids.index(job_id)) / len(all_ids)
    to_write = "%s \t %.2g \t %.2f\n" % (job_id, progress, duration)
    with open(record, "a+") as f:
        f.write(to_write)
    pass
        
    
