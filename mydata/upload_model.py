'''
data models for uploading

'''
from logger.Logger import logger
import os
import sys
import signal
import traceback
import psutil


class UploadStatus(object):
    '''
    class to hold constants. TODO replace with simpler data structure
    '''
    NOT_STARTED = 0
    IN_PROGRESS = 1
    COMPLETED = 2
    FAILED = 3
    PAUSED = 4


class UploadModel(object):
    '''
    UploadModel
    '''

    def __init__(self, data_view_id, folder_model, data_file_index):
        self.data_view_id = data_view_id
        self.folder_model = folder_model
        self.data_file_index = data_file_index
        self.folder = folder_model.GetFolder()
        self.subdirectory = folder_model.GetDataFileDirectory(data_file_index)
        self.filename = self.folder_model.GetDataFileName(data_file_index)
        self.filesize = ""  # Human-readable string displayed in data view
        self.bytes_uploaded = 0
        self.bytes_uploaded_to_staging = None
        # self.progress = 0.0  # Percentage used to render progress bar
        self._progress = 0  # Percentage used to render progress bar
        self.status = UploadStatus.NOT_STARTED
        self.message = ""
        self.buffered_reader = None
        self.scp_upload_process = None
        self._file_size = 0  # File size long integer in bytes
        self.canceled = False
        self.retries = 0
        self.verification_model = None
        self._ssh_master_process = None
        self._ssh_control_path = None
        self.scp_upload_process = None

    @property
    def progress(self):
        '''
        need a property of status update in the setter
        '''
        return self._progress

    @progress.setter
    def progress(self, progress):
        '''
        updates status if progress is not 0 or 100
        '''
        self._progress = progress
        if progress > 0 and progress < 100:
            self.status = UploadStatus.IN_PROGRESS

    @property
    def ssh_master_process(self):
        '''
        get the ssh master process from instance or the verification model
        '''
        return getattr(self, "_ssh_master_process") or \
            self.verification_model.get_ssh_master_process()

    @ssh_master_process.setter
    def ssh_master_process(self, ssh_master_process):
        '''
        setter for the magic property
        '''
        self._ssh_master_process = ssh_master_process

    @property
    def ssh_control_path(self):
        '''get ssh control path from instance or verification model'''
        return getattr(self, "_ssh_control_path") or \
            self.verification_model.GetSshControlPath()

    @ssh_control_path.setter
    def ssh_control_path(self, ssh_control_path):
        '''property setter'''
        self._ssh_control_path = ssh_control_path

    def get_relative_path_to_upload(self):
        '''
        get relative path
        '''
        return os.path.join(self.subdirectory, self.filename)

    def cancel(self):
        '''
        cancel something
        '''
        try:
            self.canceled = True
            # logger.debug("Canceling upload \"" +
            #              self.GetRelativePathToUpload() + "\".")
            if self.buffered_reader is not None:
                self.buffered_reader.close()
                logger.debug("Closed buffered reader for \"" +
                             self.get_relative_path_to_upload() +
                             "\".")
            scp_upload_process = self.scp_upload_process
            if scp_upload_process and pid_is_running(scp_upload_process.pid):
                self.scp_upload_process.terminate()
                # Check if the process has really
                # terminated and force kill if not.
                try:
                    pid = self.scp_upload_process.pid
                    # See if this throws psutil.NoSuchProcess:
                    psutil.Process(int(pid))
                    if sys.platform.startswith("win"):
                        os.kill(pid, signal.CTRL_C_EVENT)
                    else:
                        os.kill(pid, signal.SIGKILL)
                    logger.debug("Force killed SCP upload process for %s"
                                 % self.get_relative_path_to_upload())
                except psutil.NoSuchProcess:
                    logger.debug("SCP upload process for %s was terminated "
                                 "gracefully."
                                 % self.get_relative_path_to_upload())

            ssh_master_process = self.ssh_master_process
            if ssh_master_process and pid_is_running(ssh_master_process.pid):
                ssh_master_process.terminate()
                # Check if the process has really
                # terminated and force kill if not.
                try:
                    pid = self.ssh_master_process.pid
                    # See if this throws psutil.NoSuchProcess:
                    psutil.Process(int(pid))
                    if sys.platform.startswith("win"):
                        os.kill(pid, signal.CTRL_C_EVENT)
                    else:
                        os.kill(pid, signal.SIGKILL)
                    logger.debug("Force killed SCP upload process for %s"
                                 % self.get_relative_path_to_upload())
                except psutil.NoSuchProcess:
                    logger.debug("SCP upload process for %s was terminated "
                                 "gracefully."
                                 % self.get_relative_path_to_upload())
        except:
            logger.error(traceback.format_exc())

    @property
    def file_size(self):
        '''property for smart setter'''
        return self._file_size

    @file_size.setter
    def file_size(self, file_size):
        '''setting human readable size as well'''
        self._file_size = file_size
        self.filesize = humanise_size(self._file_size)

    def increment_retries(self):
        '''increment retries by 1 TODO seems superfluous'''
        self.retries += 1

    # def get_max_retries(self):
    #     '''useless method'''
    #     return 5  # FIXME: Magic number


def humanise_size(num):
    '''format size in power of 2 numbers
    TODO (should be powers of 10 on macs)'''
    for suffix in ['bytes', 'KB', 'MB', 'GB']:
        if num < 1024.0 and num > -1024.0:
            return "%3.0f %s" % (num, suffix)
        num /= 1024.0
    return "%3.0f %s" % (num, 'TB')


def pid_is_running(pid):
    '''
    check whether pid is running
    '''
    try:
        proc = psutil.Process(int(pid))
        if proc.status == psutil.STATUS_DEAD:
            return False
        if proc.status == psutil.STATUS_ZOMBIE:
            return False
        return True  # Assume other status are valid
    except psutil.NoSuchProcess:
        return False
