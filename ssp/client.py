# -*- coding: utf-8 -*-
"""
Spyder Editor

This is a temporary script file.
"""

# https://github.com/lonetwin/paramiko_talk
# https://github.com/jbardin/scp.py

import os
import sys
import time
import shlex
import zipfile
import paramiko
import numpy as np
import cryptography
from tqdm import tqdm
from numpy import spacing
from scp import SCPClient
from pathlib import Path, PurePosixPath

import warnings
warnings.filterwarnings("ignore", category=cryptography.utils.CryptographyDeprecationWarning)

import server_config as config
import server_secrets as secrets
import server # The collection of objects that are crucial to the server
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
    job_list = []
    for element in os.listdir(task_directory):
        subdir = Path(task_directory, element)
        if os.path.isdir(subdir):
            job_list.append(str(subdir))
    task_id, _ = _identity(job_list[0])
    print("%d jobs found in task '%s'" % (len(job_list), task_id))
    
    # Use that list to send jobs to the server
    ssh = _open_ssh(host=secrets.host, user=secrets.user, key=secrets.key)
    stdin, stdout, stderr = ssh.exec_command('[ -d "%s" ] && echo "exists"' % _sanitise(config.root_job / task_id))
    task_already_exists = bool(stdout.readline())
    if task_already_exists:
        ssh.close()
        raise ValueError("Task '%s' already exists in the active jobs queue. Please use a unique name" % task_id)
    else:
        scp = _open_scp(ssh, progress=True)
        # Make directories if they don't exist
        ssh.exec_command("mkdir -p %s" % _sanitise(config.root_job / task_id))
        ssh.exec_command("mkdir -p %s" % _sanitise(config.root_finished))
        ssh.exec_command("mkdir -p %s" % _sanitise(config.root_failed))
        print("Compressing task")
        local_cfile, remote_path, cfname = _zip(task_dir)
        print("Transferring task")
        scp.put(local_cfile, _sanitise(remote_path))
        scp.get(_sanitise(remote_path / cfname), os.path.split(local_cfile)[0])
        # Remote unzipping has been replaced by safer Python-handled unzipping on the server
        #unzip_cmd = 'unzip -aa -o -d "%s" "%s"' % (_sanitise(remote_path), _sanitise(remote_path / cfname))
        #stdin, stdout, stderr = ssh.exec_command(unzip_cmd)
        scp.close()
        for job_dir in job_list:
            _add_job_to_queue(job_dir)
        ssh.close()
        stop = time.time()
        print("Transfer complete in %.1f seconds" % (stop - start))
    pass




def download_results(local_dir = Path.home()/"Documents"/"SubSeaPro"):
    '''Download completed tasks to the user's computer    
    All completed tasks are identified, downloaded, and then deleted from the 
    server. '''
    ssh = _open_ssh(host=secrets.host, user=secrets.user, key=secrets.key)
    to_download = []
    stdin, stdout, stderr = ssh.exec_command('ls "%s"' % config.root_download)
    files = stdout.readlines()
    for f in files:
        n = f.strip('\n')
        if "_complete.zip" in n:
            to_download.append( n)
            task_id = n.split("_")[0]
            print("Found completed task: '%s'" % task_id)
    if to_download:
        scp = _open_scp(ssh, progress=True)
        print("Downloading")
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
    

def _open_sftp(ssh):
    sftp = paramiko.SFTPClient.from_transport(ssh.get_transport())
    return sftp
    
    
def _add_job_to_queue(local_job_dir):
    '''Based on a local job directory, add the job to the queue with sufficient
    information to proces it and identify the results at the other end'''
    t_id, j_id = _identity(local_job_dir)
    server.job.delay(t_id, j_id)
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
    task_dir = r"C:\Users\simoba\Documents\_work\NTNUIT\2019-05-22-SubSeaPro\task1"
    

    send_task_to_server(task_dir)
    download_results(task_dir)






