#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2022 Seagate Technology LLC and/or its Affiliates
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# For any questions about this software or licensing,
# please email opensource@seagate.com or cortx-questions@seagate.com.
#
#

"""common operations/methods from corio tool."""

import glob
import logging
import math
import os
import re
import shutil
import time
from base64 import b64encode
from datetime import datetime
from subprocess import Popen, PIPE, CalledProcessError
from typing import Union

import psutil as ps

from config import CLUSTER_CFG
from config import CORIO_CFG
from config import S3_CFG
from src.commons import commands as cmd
from src.commons import constants as const

LOGGER = logging.getLogger(const.ROOT)

EXEC_STATUS = {}


def log_cleanup() -> None:
    """
    Create backup of log/latest & reports.

    Renames the latest folder to a name with current timestamp and creates a folder named latest.
    Create directory inside reports and copy all old report's in it.
    """
    LOGGER.info("Backup all old execution logs into current timestamp directory.")
    now = str(datetime.now()).replace(" ", "-").replace(":", "_").replace(".", "_")
    if os.path.isdir(const.LOG_DIR):
        latest = os.path.join(const.LOG_DIR, "latest")
        if os.path.isdir(latest):
            log_list = glob.glob(latest + "/*")
            if log_list:
                os.rename(latest, os.path.join(const.LOG_DIR, now))
                LOGGER.info("Backup directory: %s", os.path.join(const.LOG_DIR, now))
            if not os.path.isdir(latest):
                os.makedirs(latest)
        else:
            os.makedirs(latest)
    else:
        LOGGER.info(
            "Created log directory '%s'",
        )
        os.makedirs(os.path.join(const.LOG_DIR, "latest"))
    LOGGER.info("Backup all old report into current timestamp directory.")
    if os.path.isdir(const.REPORTS_DIR):
        report_list = glob.glob(const.REPORTS_DIR + "/*")
        if report_list:
            now_dir = os.path.join(const.REPORTS_DIR, now)
            if not os.path.isdir(now_dir):
                os.makedirs(now_dir)
            for file in report_list:
                fpath = os.path.abspath(file)
                if os.path.isfile(fpath):
                    os.rename(file, os.path.join(now_dir, os.path.basename(fpath)))
            LOGGER.info("Backup directory: %s", now_dir)
    else:
        os.makedirs(const.REPORTS_DIR)


def cpu_memory_details() -> None:
    """Cpu and memory usage."""
    cpu_usages = ps.cpu_percent()
    if cpu_usages > 85.0:
        LOGGER.warning("Client: CPU Usages are: %s", cpu_usages)
        if cpu_usages > 98.0:
            LOGGER.critical(
                "Client: CPU usages are greater than %s, hence tool may stop execution",
                cpu_usages,
            )
    memory_usages = ps.virtual_memory().percent
    if memory_usages > 85.0:
        LOGGER.warning("Client: Memory usages are: %s", memory_usages)
        available_memory = (
            ps.virtual_memory().available * 100
        ) / ps.virtual_memory().total
        LOGGER.warning("Available Memory is: %s", available_memory)
        if memory_usages > 98.0:
            LOGGER.critical(
                "Client: Memory usages greater than %s, hence tool may stop execution",
                memory_usages,
            )
            # raise MemoryError(memory_usages)
        run_local_cmd("top -b -o +%MEM | head -n 22 > reports/topreport.txt")


def run_local_cmd(command: str) -> tuple:
    """
    Execute any given command on local machine(Windows, Linux).

    :param command: command to be executed.
    :return: bool, response.
    """
    if not command:
        raise ValueError(f"Missing required parameter: {cmd}")
    LOGGER.debug("Command: %s", cmd)
    try:
        # nosec
        with Popen(
            command, shell=True, stdout=PIPE, stderr=PIPE, encoding="utf-8"
        ) as proc:
            output, error = proc.communicate()
            LOGGER.debug("output = %s", str(output))
            LOGGER.debug("error = %s", str(error))
            if proc.returncode != 0:
                return False, error
        return True, output
    except (CalledProcessError, OSError) as error:
        LOGGER.error(error)
        return False, error


def create_file(file_name: str, size: int, data_type: Union[str, bytes] = bytes) -> str:
    """
    Create file with random data(string/bytes), default is bytes.

    :param size: Size in bytes.
    :param file_name: File name or file path.
    :param data_type: supported data type string(str)/byte(bytes) while create file.
    """
    base = const.KIB**2
    if os.path.isdir(os.path.split(file_name)[0]):
        file_path = file_name
    else:
        file_path = os.path.join(const.DATA_DIR_PATH, file_name)
    while size > base:
        if issubclass(data_type, bytes):
            with open(file_path, "ab+") as bf_out:
                bf_out.write(os.urandom(base))
        else:
            with open(file_path, "a+", encoding="utf-8") as sf_out:
                sf_out.write(b64encode(os.urandom(base)).decode("utf-8")[:base])
        size -= base
    if issubclass(data_type, bytes):
        with open(file_path, "ab+") as bf_out:
            bf_out.write(os.urandom(size))
    else:
        with open(file_path, "a+", encoding="utf-8") as sf_out:
            sf_out.write(b64encode(os.urandom(size)).decode("utf-8")[:size])
    return file_path


def convert_size(size_bytes) -> str:
    """
    Convert byte size to KiB, MiB, KB, MB etc.

    :param size_bytes: Size in bytes.
    """
    if size_bytes:
        size_name_1024 = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
        size_name_1000 = ("B", "KB", "MB", "GB", "TB", "PB")
        if (size_bytes % const.KB) == 0:
            check_pow = int(math.floor(math.log(size_bytes, const.KB)))
            power = math.pow(const.KB, check_pow)
            size = int(round(size_bytes / power, 2))
            part_size = f"{size}{size_name_1000[check_pow]}"
        elif (size_bytes % const.KIB) == 0:
            check_pow = int(math.floor(math.log(size_bytes, const.KIB)))
            power = math.pow(const.KIB, check_pow)
            size = int(round(size_bytes / power, 2))
            part_size = f"{size}{size_name_1024[check_pow]}"
        else:
            part_size = f"{size_bytes}B"
    else:
        part_size = f"{size_bytes}B"

    return part_size


def rotate_logs(dpath: str, max_count: int = 0) -> None:
    """
    Remove old logs based on creation time and keep as per max log count, default is 5.

    :param: dpath: Directory path of log files.
    :param: max_count: Maximum count of log files to keep.
    """
    max_count = max_count if max_count else CORIO_CFG.get("max_sb", 5)
    if not os.path.exists(dpath):
        raise IOError(f"Directory '{dpath}' path does not exists.")
    files = sorted(glob.glob(dpath + "/**"), key=os.path.getctime, reverse=True)
    LOGGER.debug(files)
    if len(files) > max_count:
        for fpath in files[max_count:]:
            if os.path.exists(fpath):
                if os.path.isfile(fpath):
                    os.remove(fpath)
                    LOGGER.debug("Removed: Old log file: %s", fpath)
                if os.path.isdir(fpath):
                    shutil.rmtree(fpath)
                    LOGGER.debug("Removed: Old log directory: %s", fpath)
    if len(os.listdir(dpath)) > max_count:
        raise IOError(f"Failed to rotate SB logs: {os.listdir(dpath)}")


def mount_nfs_server(host_dir: str, mnt_dir: str) -> bool:
    """
    Mount nfs server on mount directory.

    :param: host_dir: Link of NFS server with path.
    :param: mnt_dir: Path of directory to be mounted.
    """
    try:
        if not os.path.exists(mnt_dir):
            os.makedirs(mnt_dir)
            LOGGER.debug("Created directory: %s", mnt_dir)
        if host_dir:
            if not os.path.ismount(mnt_dir):
                resp = os.system(cmd.CMD_MOUNT.format(host_dir, mnt_dir))
                if resp:
                    raise IOError(f"Failed to mount server: {host_dir} on {mnt_dir}")
                LOGGER.debug(
                    "NFS Server: %s, mount on %s successfully.", host_dir, mnt_dir
                )
            else:
                LOGGER.debug("NFS Server already mounted.")
            return os.path.ismount(mnt_dir)
        LOGGER.debug("NFS Server not provided, Storing logs locally at %s", mnt_dir)
        return os.path.isdir(mnt_dir)
    except OSError as error:
        LOGGER.error(error)
        return False


def decode_bytes_to_string(text: bytes) -> Union[str, list]:
    """Convert byte to string."""
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    else:
        if isinstance(text, list):
            text_list = []
            for byt in text:
                if isinstance(byt, bytes):
                    text_list.append(byt.decode("utf-8"))
                else:
                    text_list.append(byt)
            return text_list
    return text


def setup_environment() -> None:
    """Prepare client for workload execution with CORIO."""
    LOGGER.info("Setting up environment to start execution!!")
    ret = mount_nfs_server(CORIO_CFG["nfs_server"], const.MOUNT_DIR)
    if not ret:
        raise AssertionError(f"Error while Mounting NFS directory: {const.MOUNT_DIR}.")
    if os.path.exists(const.DATA_DIR_PATH):
        shutil.rmtree(const.DATA_DIR_PATH)
    os.makedirs(const.DATA_DIR_PATH, exist_ok=True)
    LOGGER.debug("Data directory path created: %s", const.DATA_DIR_PATH)
    LOGGER.info("environment setup completed.")


def store_logs_to_nfs_local_server() -> None:
    """Copy/Store workload, support bundle and client/server resource log to local/NFS server."""
    # Copy workload execution logs to nfs/local server.
    latest = os.path.join(const.LOG_DIR, "latest")
    # copy s3bench run logs
    for fpath in glob.glob(os.path.join(os.getcwd(), "s3bench*.log")):
        if os.path.exists(fpath):
            os.rename(fpath, os.path.join(latest, os.path.basename(fpath)))
    if os.path.exists(latest):
        shutil.copytree(
            latest,
            os.path.join(const.CMN_LOG_DIR, os.getenv("run_id"), "log", "latest"),
        )
    # Copy reports to nfs/local server.
    reports = glob.glob(f"{const.REPORTS_DIR}/*.*")
    svr_report_dir = os.path.join(const.CMN_LOG_DIR, os.getenv("run_id"), "reports")
    if not os.path.exists(svr_report_dir):
        os.makedirs(svr_report_dir)
    for report in reports:
        shutil.copyfile(report, os.path.join(svr_report_dir, os.path.basename(report)))
    LOGGER.info(
        "All logs copied to %s", os.path.join(const.CMN_LOG_DIR, os.getenv("run_id"))
    )
    # Cleaning up TestData.
    if os.path.exists(const.DATA_DIR_PATH):
        shutil.rmtree(const.DATA_DIR_PATH)


def install_package(package_name: str) -> tuple:
    """Check if package installed, if not then install it."""
    resp = run_local_cmd(cmd.CMD_CHK_PKG_INSTALLED.format(package_name))
    if package_name not in resp[1]:
        run_local_cmd(cmd.CMD_INSTALL_PKG.format(package_name))
    resp = run_local_cmd(cmd.CMD_PKG_HELP.format(package_name))
    return resp


def remove_package(package_name: str) -> tuple:
    """Remove package, if installed."""
    resp = run_local_cmd(cmd.CMD_PKG_HELP.format(package_name))
    if resp[0]:
        resp = run_local_cmd(cmd.CMD_REMOVE_PKG.format(package_name))
    return resp


def get_master_details() -> tuple:
    """Get master details from cluster config."""
    host, user, passwd = None, None, None
    for node in CLUSTER_CFG["nodes"]:
        if node["node_type"] == "master":
            if not node.get("hostname", None):
                LOGGER.critical(
                    "failed to get master details: '%s'", CLUSTER_CFG["nodes"]
                )
                continue
            host, user, passwd = node["hostname"], node["username"], node["password"]
    return host, user, passwd


def get_report_file_path(corio_start_time) -> str:
    """
    Return Corio Report file path.

    :param corio_start_time: Start time for main process.
    """
    return os.path.join(
        const.REPORTS_DIR,
        f"corio_summary_{corio_start_time.strftime('%Y_%m_%d_%H_%M_%S')}.report",
    )


def convert_datetime_delta(time_delta: datetime.now()) -> str:
    """Convert datetime delta object into tuple of days, hours, minutes."""
    return (
        f"{time_delta.days}Days {time_delta.seconds//3600}Hours"
        f" {(time_delta.seconds//60)%60}Minutes"
    )


def get_test_file_path(test_id: str) -> str:
    """
    Return test log file path.

    :param test_id: Name of the test id.
    """
    fpath = ""
    for test_file in os.listdir(const.LATEST_LOG_PATH):
        if test_file.startswith(test_id):
            fpath = os.path.join(const.LATEST_LOG_PATH, test_file)
            break
    return fpath


# pylint: disable=broad-except
def retries(asyncio=True, max_retry=S3_CFG.s3max_retry, retry_delay=S3_CFG.retry_delay):
    """
    Retry/polling in case all types of failures.

    :param asyncio: True if wrapper used for asyncio else for normal function.
    :param max_retry: Max number of times retires on failure.
    :param retry_delay: Delay between two retries.
    """
    def outer_wrapper(func):
        """Outer wrapper method."""
        if asyncio:

            async def inner_wrapper(*args, **kwargs):
                """Inner wrapper method."""
                for i in reversed(range(max_retry + 1)):
                    try:
                        return await func(*args, **kwargs)
                    except Exception as err:
                        LOGGER.info("AsyncIO Function name: %s", func.__name__)
                        LOGGER.error(err, exc_info=True)
                        if i <= 1:
                            raise err
                    # Delay between each retry in seconds.
                    time.sleep(retry_delay)
                return await func(*args, **kwargs)

        else:

            def inner_wrapper(*args, **kwargs):
                """Inner wrapper method."""
                for j in reversed(range(max_retry + 1)):
                    try:
                        return func(*args, **kwargs)
                    except Exception as err:
                        LOGGER.info("Function name: %s", func.__name__)
                        LOGGER.error(err, exc_info=True)
                        if j <= 1:
                            raise err
                    # Delay between each retry in seconds.
                    time.sleep(retry_delay)
                return func(*args, **kwargs)

        return inner_wrapper

    return outer_wrapper


# pylint: disable=too-many-branches
def monitor_sessions_iterations(test_data: dict, corio_start_time, **kwargs) -> dict:
    """Monitor and update the completed sessions & iterations in execution dictionary."""
    if not EXEC_STATUS:
        for tp_data in test_data.values():
            for ts_data in tp_data.values():
                EXEC_STATUS[ts_data["TEST_ID"]] = {
                    "start_time": corio_start_time + ts_data["start_time"],
                    "min_runtime": ts_data["min_runtime"],
                    "sessions": ts_data["sessions"],
                    "iterations": 0,
                    "execution_time": None,
                    "status": None,
                }
    # pylint: disable=too-many-nested-blocks
    for tid in list(EXEC_STATUS):
        iterations = 0
        fpath = get_test_file_path(tid)
        if fpath:
            iterations = get_completed_iterations(fpath)[0]
        if datetime.now() > (
            EXEC_STATUS[tid]["start_time"] + EXEC_STATUS[tid]["min_runtime"]
        ):
            if EXEC_STATUS[tid]["status"] != "Passed":
                if kwargs.get("sequential_run"):
                    resp1 = run_local_cmd(
                        cmd.GREP_CMD.format(
                            const.COMPLETED_SESSION.format(tid), os.getenv("log_path")
                        )
                    )
                    edate = get_latest_timedelta(resp1[1])
                else:
                    prv_iteration, edate = get_completed_iterations(fpath)
                    completed_iter_count = get_completed_iterations_for_all_sessions(
                        prv_iteration, fpath
                    )
                    # 5 minute loop to check completion of ongoing iterations.
                    if CORIO_CFG.wait_on_iterations and not kwargs.get("test_failed"):
                        time_out = time.time() + 300
                        while time.time() <= time_out:
                            if (
                                completed_iter_count % EXEC_STATUS[tid]["sessions"] == 0
                                and prv_iteration != iterations
                            ):
                                break
                            time.sleep(30)
                            iterations, edate = get_completed_iterations(fpath)
                            completed_iter_count = (
                                get_completed_iterations_for_all_sessions(
                                    iterations, fpath
                                )
                            )
                    else:
                        edate = edate if edate else EXEC_STATUS[tid]["min_runtime"]
                if edate:
                    EXEC_STATUS[tid]["execution_time"] = edate
                    if not kwargs.get("test_failed"):
                        EXEC_STATUS[tid]["status"] = "Passed"
        if iterations:
            EXEC_STATUS[tid]["iterations"] = iterations
            LOGGER.info("Iteration %s completed for test %s", iterations, tid)
    return EXEC_STATUS


def get_completed_iterations_for_all_sessions(iteration: int, fpath) -> int:
    """Get the completed iteration count for all sessions."""
    resp = run_local_cmd(
        cmd.GREP_CMD.format(const.COMPLETED_ITERATIONS.format(iteration), fpath)
    )
    iter_count = len(resp[1].rstrip("\n").split("\n")) if resp[0] and resp[1] else 0
    return iter_count


def get_completed_iterations(fpath):
    """Get completed iterations from test log."""
    iterations, execution_time = 0, None
    search_string = const.COMPLETED_ITERATIONS.format(".*")
    resp = run_local_cmd(f"{cmd.GREP_CMD.format(search_string, fpath)} | tail -25")
    if resp[0] and resp[1]:
        it_str = resp[1].rsplit(search_string.rsplit("*", maxsplit=1)[-1], maxsplit=1)[
            -2
        ]
        iterations = int(re.findall(r"\d+", it_str)[-1])
        execution_time = get_latest_timedelta(resp[1])
    return iterations, execution_time


def get_latest_timedelta(log_str: str):
    """Get latest timedelta from text string."""
    sdate = re.findall(r"\d+-\d+-\d+ \d+:\d+:\d+,\d+", log_str) if log_str else ""
    execution_time = (
        datetime.strptime(sdate[-1], "%Y-%m-%d %H:%M:%S,%f") if sdate else None
    )
    return execution_time


def get_workload_list(path: str) -> list:
    """Get all workload filepath list."""
    if os.path.isdir(path):
        file_list = glob.glob(path + "/*")
    elif os.path.isfile(path):
        file_list = [os.path.abspath(path)]
    else:
        raise IOError(f"Incorrect test input: {path}")
    return file_list


def get_s3_keys(access_key: list, secret_key: list) -> dict:
    """Return mapping dict from access_keys, secret_keys."""
    if len(access_key) != len(secret_key):
        raise AssertionError(
            f"Number of access: {access_key}, secret: {secret_key} keys are different."
        )
    return dict(zip(access_key, secret_key))


def set_s3_access_secret_key(
    access_secret_keys: dict, iter_keys: iter, params: dict
) -> iter:
    """Update params dict for access secret key randomly from iterator dict."""
    try:
        params["access_key"], params["secret_key"] = next(iter_keys)
    except StopIteration:
        iter_keys = iter(access_secret_keys.items())
        params["access_key"], params["secret_key"] = next(iter_keys)
    return iter_keys
