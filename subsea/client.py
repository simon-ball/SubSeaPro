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
import zipfile
import paramiko
import numpy as np
import cryptography
from tqdm import tqdm
from celery import Celery
from scp import SCPClient
from pathlib import Path

import warnings
warnings.filterwarnings("ignore", category=cryptography.utils.CryptographyDeprecationWarning)

import subsea.server_config as config
import subsea.server_secrets as secrets
import subsea.server as server# The collection of objects that are crucial to the server
# Particularly used for server.job and server.queue


# Distinguishes tasks and jobs

# SCP speed - fixed with zip file
            
# TODO: refactor code for generating remote paths
# TODO: Improve behaviour of output zip files. 
# TODO: Transfer Ampl licence and ensure that it actually runs
# TODO: Generate non-root users, private keys, and Rabbit credentials (can that use a rsa key too?)
# TODO: Daemonise worker to be sure it comes up
# TODO: SOme means of ensuring that the server code and client code are consistent



def send_task_to_server(task_directory):
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
    returns
    -------
    none
    '''
    start = time.time()
    # Build a list of all the jobs in this task
    task_id = os.path.split(task_directory)[1]
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
        raise ValueError("Task '%s' is finished and awaiting download. Either download this taks first, or re-submit with a new name" % task_id)
    else:
        job_list = []
        for element in os.listdir(task_directory):
            subdir = Path(task_directory, element)
            if os.path.isdir(subdir):
                job_list.append(str(subdir))
        print("%d jobs found in task '%s'" % (len(job_list), task_id))
        scp = _open_scp(ssh, progress=True)
        # Make directories if they don't exist
        ssh.exec_command("mkdir -p %s" % _sanitise(config.root_job / task_id))
        ssh.exec_command("mkdir -p %s" % _sanitise(config.root_finished))
        ssh.exec_command("mkdir -p %s" % _sanitise(config.root_failed))
        ssh.exec_command("mkdir -p %s" % _sanitise(config.root_download))
        print("Compressing task")
        local_cfile, remote_path, cfname = _zip(task_dir)
        print("Transferring task")
        scp.put(local_cfile, _sanitise(remote_path))
        scp.get(_sanitise(remote_path / cfname), os.path.split(local_cfile)[0])
        # Remote unzipping has been replaced by safer Python-handled unzipping on the server
        #unzip_cmd = 'unzip -aa -o -d "%s" "%s"' % (_sanitise(remote_path), _sanitise(remote_path / cfname))
        #stdin, stdout, stderr = ssh.exec_command(unzip_cmd)
        scp.close()
#        for job_dir in job_list:
#            _add_job_to_queue(job_dir)
        _add_task_to_queue(task_id)
        ssh.close()
        stop = time.time()
        print("Transfer complete in %.1f seconds" % (stop - start))
    pass


def check_incomplete_jobs(local_dir = Path.home()/"Documents"/"SubSeaPro"/"Progress"):
    '''Check if any tasks are in progress
    If one or more tasks are in progress, then print out information about 
    current progress and expected completion time.
    Return True if jobs in progress, return False otherwise
    '''
    os.makedirs(local_dir, exist_ok=True)
    ssh = _open_ssh(host=secrets.host, user=secrets.user, key=secrets.key)
    to_download = []
    to_process = []
    stdin, stdout, stderr = ssh.exec_command('ls "%s"' % config.root_job)
    files = stdout.readlines()
    for f in files:
        n = f.strip('\n')
        if config.progress in n:
            to_download.append(n)
    if to_download:
        scp = _open_scp(ssh, progress=True)
        for prog_file in to_download:
            remote_file = _sanitise(config.root_job / prog_file)
            local_file = local_dir / prog_file
            scp.get(remote_file, local_dir)
            to_process.append(local_file)
        scp.close()
        ssh.close()
        time.sleep(0.5)
        for prog_file in to_process:
            t_id, curr_prog, expect = _read_progress_file(str(prog_file))
            if t_id:
                print("Task: %s at %.3g%%, expected complete in %s" % (t_id, curr_prog, _convert_sec(expect)))
            else:
                print("unknown")
        for prog_file in to_process:
            os.remove(str(prog_file))
        return True
    else:
        print("No tasks in progress")
        return False
            
            
        
    
    

def download_results(local_dir = Path.home()/"Documents"/"SubSeaPro"):
    '''Download completed tasks to the user's computer    
    All completed tasks are identified, downloaded, and then deleted from the 
    server. '''
    os.makedirs(local_dir, exist_ok=True)
    ssh = _open_ssh(host=secrets.host, user=secrets.user, key=secrets.key)
    to_download = []
    stdin, stdout, stderr = ssh.exec_command('ls "%s"' % config.root_download)
    files = stdout.readlines()
    for f in files:
        n = f.strip('\n')
        if config.complete in n:
            to_download.append( n)
            task_id = n.split("_")[0]
            print("Found completed task: '%s'" % task_id)
    if to_download:
        scp = _open_scp(ssh, progress=True)
        print("Downloading to %s" % local_dir)
        for task in tqdm(to_download):
            task_id = task.split("_")[0]
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
    return"%dh %dmin" % (int(sec/3600), int((sec%3600)/60))

        
    
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


def _zip(task_dir):
    '''Compress all jobs in the task to a single zip file. SCP is extremely
    inefficient at transferring many small files, so zip together for acceptable
    transfer speed. 
    '''
    t_id = _identity(task_dir)[1]
    cfilename =  _identity(task_dir)[1]+".zip"
    local_cfile = os.path.join(task_dir, cfilename)
    remote_path = config.root_job / t_id 
    cfile = zipfile.ZipFile(local_cfile, "w")
    for folder, subfolders, files in os.walk(task_dir):
        for file in files:
            for suf in config.suffixes:
                if file.endswith(suf):
                    cfile.write(os.path.join(folder, file), os.path.relpath(os.path.join(folder,file), task_dir), compress_type = zipfile.ZIP_DEFLATED)
 
    cfile.close()
    return local_cfile, remote_path, cfilename
    
    

def _add_task_to_queue(task_id):
    '''Add the task to the queue so that calculations will actually proceed'''
    server.task.delay(task_id)
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





if __name__ == '__main__':
    task_dir = r"C:\Users\simoba\Documents\_work\NTNUIT\2019-05-22-SubSeaPro\task0"

    send_task_to_server(task_dir)
#    download_results(task_dir)
#    check_incomplete_jobs()







