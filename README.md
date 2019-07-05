# SubSeaPro
A CLI queuing system for running calculations in AMPL on a remote server


## Installation

SSP uses a server-client infrastructure-, and requires installation on both systems.

### Client
Install using `pip install git+https://github.com/simon-ball/SubSeaPro`
Provide correct server_secrets:
* Rename `server_secrets.py.example` to `server_secrets.py`
* Enter the correct host address
* Enter the correct user name and path to private RSA key
* Enter correct username and password for access to the job queue


## Usage

SSP is built on the following assumptions:
	Computation takes place on Tasks, which are made up of one or more Jobs.
	A Job is a one-off calculation based on a directory containing the file "Field-Opt.run" and its associated data files
	A Task is a directory containing Jobs. A Task may contain a single job, or it may contain many jobs. 
	Within a Task, all jobs will have unique identities (directory names)
	At any given time, all Tasks existing on the server will have unique identities (directory names)
	
	
SSP Provides the following methods:
	`ssp.client.send_task_to_server(task_directory)`
		Send the task represented by `task_directory` to the server and begin calculations
		Assume that you have the following structure:
		C:\Documents\task1\job_a1b1c1
		C:\Documents\task1\job_a2b1c1
		C:\Documents\task1\job_a2b1c1
		....
		THe user would invoke `ssp.client.send_task_to_server(r"C:\Documents\task1")
		
	`ssp.client.download_results(local_dir)`
		Download _all_ completed tasks from the server to folder `local_dir` on your computer
		Tasks are downloaded as .zip files containing all jobs in the task. Within the .zip, jobs are saved in either /finished or /failed, based on whether the job completed successfully or not.
		Incomplete tasks are not downloaded
		Tasks are deleted from the server after download.
		
	