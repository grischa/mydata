import sys
import os
import subprocess
import traceback
import re
import tempfile
from datetime import datetime
import errno

from logger.Logger import logger
from Exceptions import SshException
from Exceptions import ScpException
from Exceptions import StagingHostRefusedSshConnection
from Exceptions import StagingHostSshPermissionDenied
from Exceptions import PrivateKeyDoesNotExist
from UploadModel import HumanReadableSizeString


defaultStartupInfo = None
defaultCreationFlags = 0
if sys.platform.startswith("win"):
    defaultStartupInfo = subprocess.STARTUPINFO()
    defaultStartupInfo.dwFlags |= subprocess._subprocess.STARTF_USESHOWWINDOW
    defaultStartupInfo.wShowWindow = subprocess.SW_HIDE
    import win32process
    defaultCreationFlags = win32process.CREATE_NO_WINDOW


class SmallFileUploadMethod():
    SCP = 0
    CAT = 1


class OpenSSH():
    OPENSSH_BUILD_DIR = 'openssh-5.4p1-1-msys-1.0.13'

    def DoubleQuote(self, x):
        return '"' + x.replace('"', '\\"') + '"'

    def __init__(self):
        """
        Locate the SSH binaries on various systems. On Windows we bundle a
        MinGW/MSYS build of OpenSSH.
        """
        if sys.platform.startswith("win"):
            if "HOME" not in os.environ:
                os.environ["HOME"] = os.path.expanduser('~')

        if sys.platform.startswith("win"):
            if hasattr(sys, "frozen"):
                f = lambda x, y: os.path.join(os.path.dirname(sys.executable),
                                              self.OPENSSH_BUILD_DIR, x, y)
            else:
                try:
                    mydataModulePath = \
                        os.path.dirname(pkgutil.get_loader("MyData").filename)
                except:
                    mydataModulePath = os.getcwd()
                f = lambda x, y: os.path.join(mydataModulePath,
                                              self.OPENSSH_BUILD_DIR, x, y)
            self.ssh = f("bin", "ssh.exe")
            self.scp = f("bin", "scp.exe")
            self.sshKeyGen = f("bin", "ssh-keygen.exe")
            self.cipher = "arcfour"
            self.sh = f("bin", "sh.exe")
            self.pwd = f("bin", "pwd.exe")
            self.dd = f("bin", "dd.exe")
            self.preferToUseShellInSubprocess = False
        elif sys.platform.startswith("darwin"):
            self.ssh = "/usr/bin/ssh"
            self.scp = "/usr/bin/scp"
            self.sshKeyGen = "/usr/bin/ssh-keygen"
            self.cipher = "arcfour128"
            self.dd = "/bin/dd"
            # False would be better below, but then (on POSIX
            # systems), I'd have to use command lists, instead
            # of command strings, and in some cases, I don't trust
            # subprocess to quote the command lists correctly.
            self.preferToUseShellInSubprocess = True
        else:
            self.ssh = "/usr/bin/ssh"
            self.scp = "/usr/bin/scp"
            self.sshKeyGen = "/usr/bin/ssh-keygen"
            self.cipher = "arcfour128"
            self.dd = "/bin/dd"
            # False would be better below, but then (on POSIX
            # systems), I'd have to use command lists, instead
            # of command strings, and in some cases, I don't trust
            # subprocess to quote the command lists correctly.
            self.preferToUseShellInSubprocess = True


class KeyPair():
    def __init__(self, privateKeyFilePath, publicKeyFilePath):
        self.privateKeyFilePath = privateKeyFilePath
        self.publicKeyFilePath = publicKeyFilePath
        self.publicKey = None
        self.fingerprint = None
        self.keyType = None

    def __unicode__(self):
        return "KeyPair: " + \
            str({"privateKeyFilePath": self.privateKeyFilePath,
                 "publicKeyFilePath": self.publicKeyFilePath})

    def __str__(self):
        return self.__unicode__()

    def __repr__(self):
        return self.__unicode__()

    def GetPrivateKeyFilePath(self):
        return self.privateKeyFilePath

    def ReadPublicKey(self):
        """
        Read public key, including "ssh-rsa "
        """
        if self.publicKeyFilePath is not None and \
                os.path.exists(self.publicKeyFilePath):
            with open(self.publicKeyFilePath, "r") as pubKeyFile:
                return pubKeyFile.read()
        elif os.path.exists(self.privateKeyFilePath):
            cmdList = [openSSH.sshKeyGen,
                       "-y",
                       "-f", openSSH.DoubleQuote(
                           GetMsysPath(self.privateKeyFilePath))]
            cmd = " ".join(cmdList)
            logger.debug(cmd)
            proc = subprocess.Popen(cmd,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    universal_newlines=True,
                                    startupinfo=defaultStartupInfo,
                                    creationflags=defaultCreationFlags)
            stdout, _ = proc.communicate()

            if proc.returncode != 0:
                raise SshException(stdout)

            return stdout
        else:
            raise SshException("Couldn't find MyData key files in ~/.ssh "
                               "while trying to read public key.")

    def Delete(self):
        try:
            os.unlink(self.privateKeyFilePath)
            if self.publicKeyFilePath is not None:
                os.unlink(self.publicKeyFilePath)
        except:
            logger.error(traceback.format_exc())
            return False

        return True

    def GetPublicKey(self):
        if self.publicKey is None:
            self.publicKey = self.ReadPublicKey()
        return self.publicKey

    def ReadFingerprintAndKeyType(self):
        """
        Use "ssh-keygen -yl -f privateKeyFile" to extract the fingerprint
        and key type.  This only works if the public key file exists.
        If the public key file doesn't exist, we will generate it from
        the private key file using "ssh-keygen -y -f privateKeyFile".
        """
        if not os.path.exists(self.privateKeyFilePath):
            raise PrivateKeyDoesNotExist("Couldn't find valid private key in "
                                         "%s" % self.privateKeyFilePath)
        if self.publicKeyFilePath is None:
            self.publicKeyFilePath = self.privateKeyFilePath + ".pub"
        if not os.path.exists(self.publicKeyFilePath):
            publicKey = self.GetPublicKey()
            with open(self.publicKeyFilePath, "w") as pubKeyFile:
                pubKeyFile.write(publicKey)

        if sys.platform.startswith('win'):
            quotedPrivateKeyFilePath = openSSH.DoubleQuote(GetMsysPath(self.privateKeyFilePath))
        else:
            quotedPrivateKeyFilePath = openSSH.DoubleQuote(self.privateKeyFilePath)
        cmdList = [openSSH.sshKeyGen, "-yl",
                   "-f", quotedPrivateKeyFilePath]
        cmd = " ".join(cmdList)
        logger.debug(cmd)
        # On Mac OS X, passing the entire command string (with arguments)
        # to subprocess, rather than a list requires using "shell=True",
        # otherwise Python will check whether the "file"
        # "/usr/bin/ssh-keygen -yl -f /Users/wettenhj/.ssh/MyData" exists
        # which of course it doesn't.  Passing a command list on the 
        # other hand is problematic on Windows where Python's automatic
        # quoting to convert the command list to a command doesn't always
        # work as desired.
        proc = subprocess.Popen(cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                universal_newlines=True,
                                shell=True,
                                startupinfo=defaultStartupInfo,
                                creationflags=defaultCreationFlags)
        stdout, _ = proc.communicate()

        if proc.returncode != 0:
            raise SshException(stdout)

        fingerprint = None
        keyType = None
        if stdout is not None:
            sshKeyGenOutComponents = stdout.split(" ")
            if len(sshKeyGenOutComponents) > 1:
                fingerprint = sshKeyGenOutComponents[1]
            if len(sshKeyGenOutComponents) > 3:
                keyType = sshKeyGenOutComponents[-1]\
                    .strip().strip('(').strip(')')

        return (fingerprint, keyType)

    def GetFingerprint(self):
        if self.fingerprint is None:
            self.fingerprint, self.keyType = self.ReadFingerprintAndKeyType()
        return self.fingerprint

    def GetKeyType(self):
        if self.keyType is None:
            self.fingerprint, self.keyType = self.ReadFingerprintAndKeyType()
        return self.keyType


def ListKeyPairs(keyPath=None):
    if keyPath is None:
        keyPath = os.path.join(os.path.expanduser('~'), ".ssh")
    filesInKeyPath = [f for f in os.listdir(keyPath)
                      if os.path.isfile(os.path.join(keyPath, f))]
    keyPairs = []
    for potentialKeyFile in filesInKeyPath:
        with open(os.path.join(keyPath, potentialKeyFile)) as f:
            for line in f:
                if re.search(r"BEGIN .* PRIVATE KEY", line):
                    privateKeyFilePath = os.path.join(keyPath,
                                                      potentialKeyFile)
                    publicKeyFilePath = os.path.join(keyPath,
                                                     potentialKeyFile + ".pub")
                    if not os.path.exists(publicKeyFilePath):
                        publicKeyFilePath = None
                    keyPairs.append(KeyPair(privateKeyFilePath,
                                            publicKeyFilePath))
                    break
    return keyPairs


def FindKeyPair(keyName="MyData", keyPath=None):
    if keyPath is None:
        keyPath = os.path.join(os.path.expanduser('~'), ".ssh")
    if os.path.exists(os.path.join(keyPath, keyName)):
        with open(os.path.join(keyPath, keyName)) as f:
            for line in f:
                if re.search(r"BEGIN .* PRIVATE KEY", line):
                    privateKeyFilePath = os.path.join(keyPath, keyName)
                    publicKeyFilePath = os.path.join(keyPath, keyName + ".pub")
                    if not os.path.exists(publicKeyFilePath):
                        publicKeyFilePath = None
                    return KeyPair(privateKeyFilePath, publicKeyFilePath)
                    break
    raise PrivateKeyDoesNotExist("Couldn't find valid private key in %s"
                                 % os.path.join(keyPath, keyName))


def NewKeyPair(keyName=None,
               keyPath=None,
               keyComment=None,
               startupinfo=defaultStartupInfo,
               creationflags=defaultCreationFlags):

    success = False

    if keyName is None:
        keyName = "MyData"
    if keyPath is None:
        keyPath = os.path.join(os.path.expanduser('~'), ".ssh")
    if keyComment is None:
        keyComment = "MyData Key"
    privateKeyFilePath = os.path.join(keyPath, keyName)
    publicKeyFilePath = privateKeyFilePath + ".pub"

    dotSshDir = os.path.join(os.path.expanduser('~'), ".ssh")
    if not os.path.exists(dotSshDir):
        os.makedirs(dotSshDir)

    if sys.platform.startswith('win'):
        quotedPrivateKeyFilePath = openSSH.DoubleQuote(GetMsysPath(privateKeyFilePath))
    else:
        quotedPrivateKeyFilePath = openSSH.DoubleQuote(privateKeyFilePath)
    cmdList = \
        [openSSH.sshKeyGen,
         "-f", quotedPrivateKeyFilePath,
         "-N", '""',
         "-C", openSSH.DoubleQuote(keyComment)]
    cmd = " ".join(cmdList)
    logger.debug(cmd)
    proc = subprocess.Popen(cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            shell=True,
                            startupinfo=defaultStartupInfo,
                            creationflags=defaultCreationFlags)
    stdout, _ = proc.communicate()

    if stdout is None or str(stdout).strip() == "":
        raise SshException("Received unexpected EOF from ssh-keygen.")
    elif "Your identification has been saved" in stdout:
        return KeyPair(privateKeyFilePath, publicKeyFilePath)
    elif "already exists" in stdout:
        raise SshException("Private key file \"%s\" already exists."
                           % privateKeyFilePath)
    else:
        raise SshException(stdout)

def GetSshMasterProcessAndControlPath(uploadOrVerificationModel, username,
                                      privateKeyFilePath, hostname):
    if uploadOrVerificationModel.GetSshMasterProcess():
        sshMasterProcess = uploadOrVerificationModel.GetSshMasterProcess()
        sshControlPath = uploadOrVerificationModel.GetSshControlPath()
    else:
        tempFile = tempfile.NamedTemporaryFile(delete=True)
        tempFile.close()
        if sys.platform.startswith("win"):
            sshControlPath = GetMsysPath(tempFile.name)
        else:
            sshControlPath = tempFile.name
        uploadOrVerificationModel.SetSshControlPath(sshControlPath)
        sshMasterProcessCommandString = \
            "%s -N -i %s -c %s " \
            "-oControlMaster=yes -oControlPath=%s " \
            "-oIdentitiesOnly=yes -oPasswordAuthentication=no " \
            "-oStrictHostKeyChecking=no " \
            "%s@%s" \
            % (openSSH.ssh, privateKeyFilePath,
               openSSH.cipher,
               openSSH.DoubleQuote(sshControlPath),
               username, hostname)
        logger.debug(sshMasterProcessCommandString)
        sshMasterProcess = subprocess.Popen(
            sshMasterProcessCommandString,
            shell=openSSH.preferToUseShellInSubprocess,
            startupinfo=defaultStartupInfo,
            creationflags=defaultCreationFlags)
        uploadOrVerificationModel.SetSshMasterProcess(sshMasterProcess)

    return (sshMasterProcess, sshControlPath)


def GetBytesUploadedToStaging(remoteFilePath, username, privateKeyFilePath,
                              hostname, uploadOrVerificationModel):
    if sys.platform.startswith("win"):
        privateKeyFilePath = GetMsysPath(privateKeyFilePath)
    if not remoteFilePath.startswith('"'):
        remoteFilePath = openSSH.DoubleQuote(remoteFilePath)

    sshMasterProcess, sshControlPath = \
        GetSshMasterProcessAndControlPath(uploadOrVerificationModel, username,
                                          privateKeyFilePath, hostname)

    # The authentication options below (-i privateKeyFilePath etc.) shouldn't
    # be necessary if the socket created by the SSH master process
    # (sshControlPath)is ready), but we can't guarantee that it will be
    # ready immediately.
    cmdAndArgs = [openSSH.ssh,
                  "-c", openSSH.cipher,
                  "-i", privateKeyFilePath,
                  "-oIdentitiesOnly=yes",
                  "-oPasswordAuthentication=no ",
                  "-oStrictHostKeyChecking=no ",
                  "-l", username,
                  "-oControlPath=%s " % openSSH.DoubleQuote(sshControlPath),
                  hostname,
                  openSSH.DoubleQuote("wc -c %s" % remoteFilePath)]
    cmdString = " ".join(cmdAndArgs)
    logger.debug(cmdString)
    proc = subprocess.Popen(cmdString,
                            shell=openSSH.preferToUseShellInSubprocess,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            startupinfo=defaultStartupInfo,
                            creationflags=defaultCreationFlags)
    stdout, _ = proc.communicate()
    lines = stdout.splitlines()
    bytesUploaded = 0
    for line in lines:
        match = re.search(r"^(\d+)\s+\S+", line)
        if match:
            bytesUploaded = long(match.groups()[0])
            return bytesUploaded
        elif "No such file or directory" in line:
            bytesUploaded = 0
            return bytesUploaded
        elif line == "ssh_exchange_identification: read: " \
                "Connection reset by peer" or \
                line == "ssh_exchange_identification: " \
                        "Connection closed by remote host":
            # print "Encountered ssh_exchange_identification error for %s." % remoteFilePath
            message = "The MyTardis staging host assigned to your " \
                "MyData instance (%s) refused MyData's attempted " \
                "SSH connection." \
                "\n\n" \
                "There are a few possible reasons why this could occur." \
                "\n\n" \
                "1. Your MyTardis administrator could have forgotten to " \
                "grant your IP address access to MyTardis's staging " \
                "host, or" \
                "\n\n" \
                "2. Your IP address could have changed sinced you were " \
                "granted access to MyTardis's staging host, or" \
                "\n\n" \
                "3. MyData's attempts to log in to MyTardis's staging host " \
                "could have been flagged as suspicious, and your IP " \
                "address could have been temporarily banned." \
                "\n\n" \
                "4. MyData could be running more simultaneous upload threads " \
                "than your staging server can handle.  Ask your staging server " \
                "administrator to check the values of MaxStartups and MaxSessions " \
                "in the server's /etc/ssh/sshd_config" \
                "\n\n" \
                "In any of these cases, it is best to contact your " \
                "MyTardis administrator for assistance." % hostname
            logger.error(stdout)
            logger.error(message)
            raise StagingHostRefusedSshConnection(message)
        elif line == "Permission denied (publickey,password).":
            message = "MyData was unable to authenticate into the " \
                "MyTardis staging host assigned to your MyData instance " \
                "(%s)." \
                "\n\n" \
                "There are a few possible reasons why this could occur." \
                "\n\n" \
                "1. Your MyTardis administrator could have failed to add " \
                "the public key generated by your MyData instance to the " \
                "appropriate ~/.ssh/authorized_keys file on MyTardis's " \
                "staging host, or" \
                "\n\n" \
                "2. The private key generated by MyData (a file called " \
                "\"MyData\" in the \".ssh\" folder within your " \
                "user home folder (%s) could have been deleted or moved." \
                "\n\n" \
                "3. The permissions on %s could be too open - only the " \
                "current user account should be able to access this private " \
                "key file." \
                "\n\n" \
                "In any of these cases, it is best to contact your " \
                "MyTardis administrator for assistance." \
                % (hostname, os.path.expanduser("~"),
                   os.path.join(os.path.expanduser("~"), ".ssh",
                                "MyData"))

            logger.error(message)
            raise StagingHostSshPermissionDenied(message)
        else:
            logger.debug(line)
    return bytesUploaded


def UploadFile(filePath, fileSize, username, privateKeyFilePath,
               hostname, remoteFilePath, ProgressCallback,
               foldersController, uploadModel):
    """
    We want to ensure that the partially uploaded datafile in MyTardis's
    staging area always has a whole number of chunks.  If we were to
    append each chunk directly to the datafile at the same time as
    sending it over the SSH channel, there would be a risk of a broken
    connection resulting in a partial chunk being appended to the datafile.
    So we upload the chunk to its own file on the remote server first,
    and then append the chunk onto the remote (partial) datafile.

    The file may have already been uploaded, so let's check
    for it (and check its size) on the server. We don't use
    checksums here because they are slow for large files,
    and ultimately it will be the MyTardis verification
    task which does the final check.
    """

    bytesUploaded = 0
    largeFileSize = 10 * 1024 * 1024  # FIXME: Magic number

    if fileSize > largeFileSize:
        ProgressCallback(None, bytesUploaded, fileSize,
                         message="Checking for a previous partial upload...")
        if uploadModel.GetBytesUploadedToStaging() is not None:
            bytesUploaded = uploadModel.GetBytesUploadedToStaging()
        else:
            bytesUploaded = GetBytesUploadedToStaging(remoteFilePath,
                                                      username, privateKeyFilePath,
                                                      hostname, uploadModel)
            uploadModel.SetBytesUploadedToStaging(bytesUploaded)
    if 0 < bytesUploaded < fileSize:
        ProgressCallback(None, bytesUploaded, fileSize,
                         message="Found %s uploaded previously"
                         % HumanReadableSizeString(bytesUploaded))
    if foldersController.IsShuttingDown() or uploadModel.Canceled():
        logger.debug("UploadFile 1: Aborting upload for "
                     "%s" % filePath)
        return
    if bytesUploaded == fileSize:
        logger.debug("UploadFile returning because file \"%s\" has already "
                     "been uploaded." % filePath)
        return
    elif bytesUploaded > fileSize:
        logger.error("Possibly due to a bug in MyData, the file size on "
                     "the remote server is larger than the local file size "
                     "for \"%s\"." % filePath)
    elif 0 < bytesUploaded < fileSize:
        logger.info("MyData will attempt to resume the partially "
                    "completed upload for \"%s\"..." % filePath)
    elif bytesUploaded == 0:
        # The most common use case.
        pass

    if sys.platform.startswith("win"):
        privateKeyFilePath = GetMsysPath(privateKeyFilePath)

    remoteChunkPath = remoteFilePath + ".chunk"

    # logger.warning("Assuming that the remote shell is Bash.")

    sshMasterProcess, sshControlPath = \
        GetSshMasterProcessAndControlPath(uploadModel, username,
                                          privateKeyFilePath, hostname)

    remoteRemoveChunkCommand = \
        "/bin/rm -f %s" % openSSH.DoubleQuote(remoteChunkPath)
    rmCommandString = \
        "%s -i %s -c %s " \
        "-oControlPath=%s " \
        "-oIdentitiesOnly=yes -oPasswordAuthentication=no " \
        "-oStrictHostKeyChecking=no " \
        "%s@%s %s" \
        % (openSSH.ssh, privateKeyFilePath, openSSH.cipher,
           openSSH.DoubleQuote(sshControlPath),
           username, hostname,
           openSSH.DoubleQuote(remoteRemoveChunkCommand))
    # logger.debug(rmCommandString)
    removeRemoteChunkProcess = \
        subprocess.Popen(rmCommandString,
                         shell=openSSH.preferToUseShellInSubprocess,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT,
                         startupinfo=defaultStartupInfo,
                         creationflags=defaultCreationFlags)
    stdout, _ = removeRemoteChunkProcess.communicate()
    if removeRemoteChunkProcess.returncode != 0:
        raise SshException(stdout, removeRemoteChunkProcess.returncode)

    # defaultChunkSize = 1024*1024  # FIXME: magic number
    defaultChunkSize = 128*1024  # FIXME: magic number
    maxChunkSize = 16*1024*1024  # FIXME: magic number
    chunkSize = defaultChunkSize
    # FIXME: magic number (approximately 50 progress bar increments)
    while (fileSize / chunkSize) > 50 and chunkSize < maxChunkSize:
        chunkSize = chunkSize * 2
    # with open(filePath, 'rb') as fp:
    skip = 0
    if 0 < bytesUploaded < fileSize and (bytesUploaded % chunkSize == 0):
        ProgressCallback(None, bytesUploaded, fileSize,
                         message="Performing seek on file, so we can "
                         "resume the upload.")
        # fp.seek(bytesUploaded)
        skip = bytesUploaded / chunkSize
        ProgressCallback(None, bytesUploaded, fileSize)
    else:
        # Overwrite staging file if it is bigger that local file:
        bytesUploaded = 0

    # FIXME: Handle exception where socket for ssh control path
    # is missing, then we need to create a new master connection.

    while bytesUploaded < fileSize:
        # for chunk in iter(lambda: fp.read(chunkSize), b''):
            if foldersController.IsShuttingDown() or uploadModel.Canceled():
                logger.debug("UploadLargeFile 1: Aborting upload for "
                             "%s" % filePath)
                sshMasterProcess.terminate()
                return

            # Write chunk to temporary file:
            chunkFile = tempfile.NamedTemporaryFile(delete=False)
            # chunkFile.write(chunk)
            chunkFile.close()
            if sys.platform.startswith("win"):
                chunkFilePath = GetMsysPath(chunkFile.name)
            else:
                chunkFilePath = chunkFile.name

            ddCommandString = \
                "%s bs=%d skip=%d count=1 if=%s of=%s" \
                % (openSSH.dd,
                   chunkSize,
                   skip,
                   openSSH.DoubleQuote(filePath),
                   openSSH.DoubleQuote(chunkFilePath))
            # logger.debug(ddCommandString)
            ddProcess = subprocess.Popen(
                ddCommandString,
                shell=openSSH.preferToUseShellInSubprocess,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                startupinfo=defaultStartupInfo,
                creationflags=defaultCreationFlags)
            stdout, _ = ddProcess.communicate()
            if ddProcess.returncode != 0:
                raise Exception(stdout,
                                   ddCommandString,
                                   ddProcess.returncode)
            lines = stdout.splitlines()
            bytesTransferred = 0
            for line in lines:
                match = re.search(r"^(\d+)\s+bytes\s+transferred.*$", line)
                if match:
                    bytesTransferred = long(match.groups()[0])
            skip += 1

            scpCommandString = \
                '%s -i %s -c %s ' \
                '-oControlPath=%s ' \
                '-oIdentitiesOnly=yes -oPasswordAuthentication=no ' \
                '-oStrictHostKeyChecking=no ' \
                '%s "%s@%s:\\"%s\\""' \
                % (openSSH.scp,
                   privateKeyFilePath,
                   openSSH.cipher,
                   openSSH.DoubleQuote(sshControlPath),
                   chunkFilePath,
                   username, hostname,
                   remoteChunkPath)
            # logger.debug(scpCommandString)
            scpUploadChunkProcess = subprocess.Popen(
                scpCommandString,
                shell=openSSH.preferToUseShellInSubprocess,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                startupinfo=defaultStartupInfo,
                creationflags=defaultCreationFlags)
            uploadModel.SetScpUploadProcess(scpUploadChunkProcess)
            stdout, _ = scpUploadChunkProcess.communicate()
            if scpUploadChunkProcess.returncode != 0:
                raise ScpException(stdout,
                                   scpCommandString,
                                   scpUploadChunkProcess.returncode)

            try:
                os.unlink(chunkFile.name)
            except:
                logger.error(traceback.format_exc())

            # Append chunk to remote datafile.
            # FIXME: Investigate whether using an ampersand to put
            # remote cat process in the background helps to make things
            # more robust in the case of an interrupted connection.
            # On Windows, we might need to escape the ampersand with a
            # caret (^&)

            if bytesUploaded > 0:
                redirect = ">>"
            else:
                redirect = ">"
            remoteCatCommand = \
                "cat %s %s %s" % (openSSH.DoubleQuote(remoteChunkPath),
                                  redirect,
                                  openSSH.DoubleQuote(remoteFilePath))
            catCommandString = \
                "%s -i %s -c %s " \
                "-oControlPath=%s " \
                "-oIdentitiesOnly=yes -oPasswordAuthentication=no " \
                "-oStrictHostKeyChecking=no " \
                "%s@%s %s" \
                % (openSSH.ssh, privateKeyFilePath,
                   openSSH.cipher,
                   openSSH.DoubleQuote(sshControlPath),
                   username, hostname,
                   openSSH.DoubleQuote(remoteCatCommand))
            # logger.debug(catCommandString)
            appendChunkProcess = subprocess.Popen(
                catCommandString,
                shell=openSSH.preferToUseShellInSubprocess,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                startupinfo=defaultStartupInfo,
                creationflags=defaultCreationFlags)
            stdout, _ = appendChunkProcess.communicate()
            if appendChunkProcess.returncode != 0:
                raise SshException(stdout, appendChunkProcess.returncode)

            bytesUploaded += bytesTransferred
            ProgressCallback(None, bytesUploaded, fileSize)

            if foldersController.IsShuttingDown() or uploadModel.Canceled():
                logger.debug("UploadLargeFile 2: Aborting upload for "
                             "%s" % filePath)
                sshMasterProcess.terminate()
                return

    remoteRemoveChunkCommand = \
        "/bin/rm -f %s" % openSSH.DoubleQuote(remoteChunkPath)
    rmCommandString = \
        "%s -i %s -c %s " \
        "-oControlPath=%s " \
        "-oIdentitiesOnly=yes -oPasswordAuthentication=no " \
        "-oStrictHostKeyChecking=no " \
        "%s@%s %s" \
        % (openSSH.ssh, privateKeyFilePath, openSSH.cipher,
           openSSH.DoubleQuote(sshControlPath),
           username, hostname,
           openSSH.DoubleQuote(remoteRemoveChunkCommand))
    # logger.debug(rmCommandString)
    removeRemoteChunkProcess = \
        subprocess.Popen(rmCommandString,
                         shell=openSSH.preferToUseShellInSubprocess,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT,
                         startupinfo=defaultStartupInfo,
                         creationflags=defaultCreationFlags)
    stdout, _ = removeRemoteChunkProcess.communicate()
    if removeRemoteChunkProcess.returncode != 0:
        sshMasterProcess.terminate()
        raise SshException(stdout, removeRemoteChunkProcess.returncode)

    sshMasterProcess.terminate()


def GetMsysPath(path):
    """
    Converts "C:\path\\to\\file" to "/C/path/to/file".
    """
    realpath = os.path.realpath(path)
    match = re.search(r"^(\S):(.*)", realpath)
    if match:
        return "/" + match.groups()[0] + match.groups()[1].replace("\\", "/")
    else:
        raise Exception("OpenSSH.GetMsysPath: %s doesn't look like "
                        "a valid path." % path)

openSSH = OpenSSH()
ssh = openSSH.ssh
scp = openSSH.scp
sshKeyGen = openSSH.sshKeyGen
if sys.platform.startswith("win"):
    sh = openSSH.sh
    pwd = openSSH.pwd
