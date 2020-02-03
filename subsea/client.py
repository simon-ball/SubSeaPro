# -*- coding: utf-8 -*-
"""
Spyder Editor

This is a temporary script file.
"""

# https://github.com/lonetwin/paramiko_talk
# https://github.com/jbardin/scp.py

import os
import time
import shlex
import pathlib
import zipfile
import paramiko
import numpy as np
import cryptography
from tqdm import tqdm
from celery import Celery
from scp import SCPClient


import warnings
warnings.filterwarnings("ignore", category=cryptography.utils.CryptographyDeprecationWarning)

import subsea.server_config as config
import subsea.server_secrets as secrets
import subsea.server as server# The collection of objects that are crucial to the server
# Particularly used for server.job and server.queue


def send_task_to_server(task_directory, recipient=None, remote_name=None):
    '''Send the provided list of jobs to the server for processing
    
    params
    ------
    task_directory : path-like
        Directory storing the jobs in this path (might be 1 job or many)
        For example, assume you have the following structure 
            C:\MyDcuments\Task1\a1b1c1\Field-Opt.run
            C:\MyDcuments\Task1\a1b1c2\Field-Opt.run
            ....... etc
        then task_directory = C:\MyDcuments\Task1
    recipient : str or list of str
        Email addresses to be notified on completion of job
    returns
    -------
    none
    '''
    if type(task_directory) not in (pathlib.Path, pathlib.WindowsPath, pathlib.PosixPath):
        task_directory = pathlib.Path(task_directory)
    start = time.time()
    # Build a list of all the jobs in this task
    if remote_name is None:
        task_id = task_directory.name
    else:
        task_id = remote_name
    if not task_id:
        raise ValueError("Your task directory is not a valid value. Please ensure that it points to a known directory and has no trailing slashes")
    
    # Use that list to send jobs to the server
    ssh = _open_ssh(host=secrets.host, user=secrets.user, key=secrets.key)
    _, stdout_job, _ = ssh.exec_command('[ -d "%s" ] && echo "exists"' % _sanitise(config.root_job / task_id))
    _, stdout_down, _ = ssh.exec_command('[ -e "%s" ] && echo "exists"' % _sanitise(config.root_download / (task_id+config.complete)))
    task_in_progress = bool(stdout_job.readline())
    task_finished = bool(stdout_down.readline())
    if task_in_progress:
        ssh.close()
        raise ValueError("Task '%s' is already in progress. Please ensure that new jobs use a unique name" % task_id)
    elif task_finished:
        ssh.close()
        raise ValueError("Task '%s' is finished and awaiting download. Either download this task first, or re-submit with a new name" % task_id)
    else:
        print(f"=== Sending task '{task_id}' to server ===")
        job_list = []
        for element in os.listdir(task_directory):
            subdir = task_directory / element
            if subdir.is_dir():
                job_list.append(subdir)
        print("%d jobs found in task '%s'" % (len(job_list), task_id))
        scp = _open_scp(ssh, progress=True)
        # Make directories if they don't exist
        ssh.exec_command("mkdir -p %s" % _sanitise(config.root_job / task_id))
        ssh.exec_command("mkdir -p %s" % _sanitise(config.root_finished))
        ssh.exec_command("mkdir -p %s" % _sanitise(config.root_failed))
        ssh.exec_command("mkdir -p %s" % _sanitise(config.root_download))
        print("Compressing task")
        local_cfile, remote_path, cfname = _zip(task_directory, remote_name)
        print("Transferring task")
        scp.put(str(local_cfile), _sanitise(remote_path))
        scp.close()
        _add_task_to_queue(task_id, recipient)
        ssh.close()
        stop = time.time()
        print("Transfer complete in %.1f seconds \n" % (stop - start))
    pass


def check_status(local_dir = pathlib.Path.home()/"Documents"/"SubSeaPro"/"Progress"):
    '''CHeck on the status of the queue 
    
    tasks actively in progress will have a file /jobs/{taskid}_progress.txt
    Tasks not yet begun will have a folder but no _progress.txt
    Tasks completed exist as zip files in /download
    
    Parameters
    ----------
    local_dir : pathlib.Path
        OPTIONAL: Temporary working folder
    
    Returns
    -------
    int
        How many jobs are currently in progress
    Int
        How many jobs are in the queue, not yet started
    Int
        How many completed jobs are ready to be downloaded
    '''
    os.makedirs(local_dir, exist_ok=True)
    ssh = _open_ssh(host=secrets.host, user=secrets.user, key=secrets.key)
    scp = _open_scp(ssh, progress=True)
    to_download = []
    to_process = []
    to_queue = []
    # Check on tasks that are queued to be done: they exist in config.root_job
    stdin, stdout, stderr = ssh.exec_command('ls "%s"' % config.root_job)
    tasks_in_progress = stdout.readlines() # list of task directories in /jobs
    for f in tasks_in_progress:
        name = f.strip('\n')
        if config.progress in name:
            to_download.append(name)
            task_id = name[:-1*len(config.progress)]
            try:
                to_queue.remove(task_id)
            except ValueError: # element not in list
                pass
        else:
            task_id = name
            to_queue.append(task_id)
    print("=== Tasks in progress ===")
    if to_download:
        for progress_file in to_download:
            remote_file = _sanitise(config.root_job / progress_file)
            local_file = local_dir / progress_file
            scp.get(remote_file, local_dir)
            to_process.append(local_file)
        time.sleep(0.5)
        for prog_file in to_process:
            t_id, curr_prog, expect = _read_progress_file(str(prog_file))
            if t_id:
                print("Task: '%s' at %.3g%%, expected complete in %s" % (t_id, curr_prog, _convert_sec(expect)))
            else:
                print("unknown")
        for prog_file in to_process:
            os.remove(str(prog_file))
    else:
        print("None")
    print("=== Tasks in queue ===")
    if to_queue:
        for task_id in to_queue:
            print(f"Task: '{task_id}' queued")
    else:
        print("None")
    #Check on tasks to be downloaded
    stdin, stdout, stderr = ssh.exec_command('ls "%s"' % config.root_download)
    completed = stdout.readlines()
    print("=== Tasks completed ===")
    if completed:
        for f in completed:
            name = f.strip('\n')
            if config.complete in name:
                task_id = name[:-1*len(config.complete)]
                print(f"Task: '{task_id}' complete")
    else:
        print("No finished tasks")
    scp.close()
    ssh.close()
    return len(to_download), len(to_queue), len(completed)
            
            
        
    
    

def download_results(local_dir = pathlib.Path.home()/"Documents"/"SubSeaPro", pattern=None):
    '''Download completed tasks to the user's computer    
    All completed tasks are identified, downloaded, and then deleted from the 
    server. 
    
    The local directory must not contain files with the same name as completed 
    tasks. If there exist files with the same name, an error will be raised and
    no files will be downloaded
    
    Parameters
    ----------
    local_dir : path-like
        Local directory to which completed results are downloaded. Defaults to 
        the users Documents folder
    
    '''
    if type(local_dir) not in (pathlib.Path, pathlib.WindowsPath, pathlib.PosixPath):
        local_dir = pathlib.Path(local_dir)
    os.makedirs(local_dir, exist_ok=True)
    ssh = _open_ssh(host=secrets.host, user=secrets.user, key=secrets.key)
    to_download = []
    stdin, stdout, stderr = ssh.exec_command('ls "%s"' % config.root_download)
    files = stdout.readlines()
    for f in files:
        name = f.strip('\n')
        if config.complete in name:
            if (pattern is None) or (pattern in name):
                to_download.append(name)
                task_id = name[:-1*len(config.complete)]
                print("Found completed task: '%s'" % task_id)
            elif pattern is not None:
                print("No completed tasks matching pattern '%s'" % pattern)
    if to_download:
        local_files = os.listdir(local_dir)
        for task in to_download:
            if task in local_files:
                raise NameError(f"A file with the name {task} already exists in the local directory"\
                                f" ({local_dir}). Move or rename the local file first to avoid over-writing")
        scp = _open_scp(ssh, progress=True)
        print("Downloading to %s" % local_dir)
        for task in tqdm(to_download):
            remote_file = _sanitise(config.root_download / task)
            scp.get(remote_file, local_dir )       
        
        scp.close()
        for task in to_download:
            ssh.exec_command('rm "%s"' % _sanitise(config.root_download / task))
        print("All completed tasks downloaded")
    else:
        print("No completed tasks to download")
    ssh.close()
    return True




###############################################################################
###################             HELPER FUNCTIONS
###############################################################################
    
def _sanitise(text):
    '''Use the shlex library to safely escape **most** dangerous inputs before 
    calling them at the commandline'''
    return shlex.quote(str(text))

def _identity(job_dir):
    job_identity = os.path.split(job_dir)[1]
    task_identity = os.path.split((os.path.split(job_dir)[-0]))[1]
    return task_identity, job_identity

def _convert_sec(sec):
    try:
        string = "%dh %dmin" % (int(sec/3600), int((sec%3600)/60))
        return string
    except:
        return "unknown"

        
    
def _read_progress_file(file_name):
    '''Based on a progress file downloaded from the server, get the current
    progress as a % and the expected completion time'''
    task_id = os.path.split(file_name)[1][:-1*len(config.progress)]
    try:
        text = np.genfromtxt(file_name, dtype=str, delimiter="\t")
        t = text[:,2].astype(float)
        progress = text[:,1].astype(float)
        current_progress = progress[-1]
        duration = np.sum(t)
        predicted_duration = duration / current_progress
        remaining = predicted_duration - duration
        predicted_endpoint = time.time() + remaining
        predicted_endpoint_dt = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(predicted_endpoint))
        return task_id, current_progress*100, remaining
    except:
        return task_id, 0, np.nan


def _zip(task_dir, remote_name=None):
    '''Compress all jobs in the task to a single zip file. SCP is extremely
    inefficient at transferring many small files, so zip together for acceptable
    transfer speed. 
    Parameters
    ----------
    task_dir : pathlib.Path
        location of the task, e.g. C:\Documents\task0
    remote_name : str
        optional - rename the task on the server
    Returns
    -------
    local_cfile : pathlib.Path
        Local compressed file, e.g. C:\Documents\task0.zip
    remote_path : pathlib.PurePosixPath
        Remote file location, e.g. /jobs/task0
    cfilename : pathlib.Path
        Local compressed file name, e.g. task0.zip
    '''
    if remote_name is not None:
        t_id = remote_name
    else:
        t_id = task_dir.name
    cfilename =  f"{t_id}.zip"
    local_cfile = task_dir.parent / cfilename
    remote_path = config.root_job / t_id 
    cfile = zipfile.ZipFile(local_cfile, "w")
    for folder, subfolders, files in os.walk(task_dir):
        for file in files:
            for suf in config.suffixes:
                if file.endswith(suf):
                    cfile.write(os.path.join(folder, file), os.path.relpath(os.path.join(folder,file), task_dir), compress_type = zipfile.ZIP_DEFLATED)
    cfile.close()
    return local_cfile, remote_path, cfilename
    
    

def _add_task_to_queue(task_id, recipient):
    '''Add the task to the queue so that calculations will actually proceed'''
    server.task.delay(task_id, recipient)
    pass



def _open_ssh(host, user, key):
    '''Use the paramiko library t =o connect to the remote host by SSH, 
    authenticating with an RSA private key
    
    The SSH connection can later be called with ssh.close()
    Parameters:
    ----------
    host : str
        hostname or IP address
    user : str
        Username to connect to
    key : path
        Path to the private key file, typically in the .pem format
    '''
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host,
            key_filename=key,
            username=user)
    return ssh

def _open_scp(ssh, progress = False):
    '''Piggyback an SCP client over the provided ssh session.
    Main methods of SCP are:
        put(local_file, remote_file)
        get(remote_file, local_file)
        close()
    progress: show a progress bar for each file that is transferred?
    '''
    
    if progress:
        scp = SCPClient(ssh.get_transport(), progress=_progress)
    else:
        scp = SCPClient(ssh.get_transport())
    return scp



# Define progress callback that prints the current percentage completed for the file
def _progress(filename, size, sent):
    '''This seems pointless, but the idea is to enforce that scp blocks until 
    the transfer is complete'''
    #sys.stdout.write("%s\'s progress: %.2f%%   \n" % (filename, float(sent)/float(size)*100) )
    #progress = float(size)/float(sent+spacing(1))
    time.sleep(0.001)
    pass






