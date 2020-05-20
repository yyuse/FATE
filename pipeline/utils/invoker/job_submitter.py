#
#  Copyright 2019 The FATE Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

import json
import os
import subprocess
import tempfile
import time
from pipeline.backend import config as conf
from pipeline.backend.config import JobStatus
from pipeline.backend.config import StatusCode


FATE_HOME = os.getcwd() + "/../../"
FATE_FLOW_CLIENT = FATE_HOME + "fate_flow/fate_flow_client.py"


class JobFunc:
    SUMMIT_JOB = "submit_job"
    UPLOAD = "upload"
    COMPONENT_OUTPUT_MODEL = "component_output_model"
    COMPONENT_METRIC = "component_metric_all"
    JOB_STATUS = "query_job"
    TASK_STATUS = "query_task"
    COMPONENT_OUTPUT_DATA = "component_output_data"


class JobInvoker(object):
    def __init__(self):
        pass

    @classmethod
    def _run_cmd(cls, cmd, output_while_running=False):
        subp = subprocess.Popen(cmd,
                                shell=False,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        if not output_while_running:
            stdout, stderr = subp.communicate()
            return stdout.decode("utf-8")
        else:
            for line in subp.stdout:
                if line == "":
                    continue
                else:
                    print(line.strip())

    def submit_job(self, dsl=None, submit_conf=None):
        with tempfile.TemporaryDirectory() as job_dir:
            if dsl:
                dsl_path = os.path.join(job_dir, "job_dsl.json")
                import pprint
                pprint.pprint(dsl)
                with open(dsl_path, "w") as fout:
                    fout.write(json.dumps(dsl))

            submit_path = os.path.join(job_dir, "job_runtime_conf.json")
            with open(submit_path, "w") as fout:
                fout.write(json.dumps(submit_conf))

            cmd = ["python", FATE_FLOW_CLIENT,
                   "-f", JobFunc.SUMMIT_JOB,
                   "-c", submit_path]

            if dsl:
                cmd.extend(["-d", dsl_path])

            result = self._run_cmd(cmd)
            try:
                result = json.loads(result)
                if 'retcode' not in result or result["retcode"] != 0:
                    raise ValueError

                if "jobId" not in result:
                    raise ValueError

                job_id = result["jobId"]
                data = result["data"]
            except ValueError:
                raise ValueError("job submit failed, err msg: {}".format(result))

        return job_id, data

    def upload_data(self, submit_conf=None, drop=0):
        if submit_conf:
            file_path = submit_conf["file"]
            submit_conf["file"] = os.path.join(FATE_HOME, file_path)
        with tempfile.TemporaryDirectory() as job_dir:
            submit_path = os.path.join(job_dir, "job_runtime_conf.json")
            with open(submit_path, "w") as fout:
                fout.write(json.dumps(submit_conf))

            cmd = ["python", FATE_FLOW_CLIENT,
                   "-f", JobFunc.UPLOAD,
                   "-c", submit_path,
                   "-drop", str(drop)
                  ]

            result = self._run_cmd(cmd)
            try:
                result = json.loads(result)
                if 'retcode' not in result or result["retcode"] != 0:
                    raise ValueError

                if "jobId" not in result:
                    raise ValueError

                job_id = result["jobId"]
                data = result["data"]
            except ValueError:
                raise ValueError("job submit failed, err msg: {}".format(result))

        return job_id, data

    def monitor_job_status(self, job_id, role, party_id):
        while True:
            ret_code, ret_msg, data = self.query_job(job_id, role, party_id)
            status = data["f_status"]
            if status == JobStatus.SUCCESS:
                print ("job is success!!!")
                return StatusCode.SUCCESS

            if status == JobStatus.FAIL:
                print ("job is failed, please check out job {} by fate board or fate_flow cli".format(job_id))
                return StatusCode.FAIL

            if status == JobStatus.WAITING:
                print ("job {} is still waiting")

            if status == JobStatus.RUNNING:
                print ("job {} now is running component {}".format(job_id, data["f_current_tasks"]))

            time.sleep(conf.TIME_QUERY_FREQS)

    def query_job(self, job_id, role, party_id):
        cmd = ["python", FATE_FLOW_CLIENT,
               "-f", JobFunc.JOB_STATUS,
               "-j", job_id,
               "-r", role,
               "-p", str(party_id)]

        result = self._run_cmd(cmd)
        try:
            result = json.loads(result)
            if 'retcode' not in result:
                raise  ValueError("can not query_job")

            ret_code = result["retcode"]
            ret_msg = result["retmsg"]
            print(f"query job result is {result}")
            data = result["data"][0]
            return ret_code, ret_msg, data
        except ValueError:
            raise ValueError("query job result is {}, can not parse useful info".format(result))

    def query_task(self, job_id, cpn_name, role, party_id):
        cmd = ["python", FATE_FLOW_CLIENT,
               "-f", JobFunc.SUMMIT_JOB,
               "-j", job_id,
               "-cpn", cpn_name,
               "-r", role,
               "-p", party_id]

        result = self._run_cmd(cmd)
        try:
            result = json.loads(result)
            if 'retcode' not in result:
                raise  ValueError("can not query component {}' task status".format(cpn_name))

            ret_code = result["retcode"]
            ret_msg = result["retmsg"]

            data = result["data"]
            return ret_code, ret_msg, data
        except ValueError:
            raise ValueError("query task result is {}, can not parse useful info".format(result))

    def get_output_data(self, job_id, cpn_name, role, party_id, limits=None):
        with tempfile.TemporaryDirectory() as job_dir:
            cmd = ["python", FATE_FLOW_CLIENT,
                   "-f", JobFunc.COMPONENT_OUTPUT_DATA,
                   "-j", job_id,
                   "-cpn", cpn_name,
                   "-r", role,
                   "-p", str(party_id),
                   "-o", job_dir]

            result = self._run_cmd(cmd)
            result = json.loads(result)
            output_dir = result["directory"]
            # output_data_meta = os.path.join(output_dir, "output_data_meta.json")
            output_data = os.path.join(output_dir, "output_data.csv")
            # header = None
            # with open(output_data_meta, "r") as fin:
            #    header = json.loads(fin.read())["header"]
            # data = [header]

            data = []
            with open(output_data, "r") as fin:
                for line in fin:
                    data.append(line.strip())

            print (data[:10])
            return data

    def get_model_param(self, job_id, cpn_name, role, party_id):
        result = None
        try:
            cmd = ["python", FATE_FLOW_CLIENT,
                   "-f", JobFunc.COMPONENT_OUTPUT_MODEL,
                   "-j", job_id,
                   "-cpn", cpn_name,
                   "-r", role,
                   "-p", str(party_id)]

            result = self._run_cmd(cmd)
            result = json.loads(result)
            if "data" not in result:
                print ("job {}, component {} has no output model param".format(job_id, cpn_name))
                return
            return result["data"]
        except:
            print ("Can not get output model, err msg is {}".format(result))

    def get_metric(self, job_id, cpn_name, role, party_id):
        result = None
        try:
            cmd = ["python", FATE_FLOW_CLIENT,
                   "-f", JobFunc.COMPONENT_METRIC,
                   "-j", job_id,
                   "-cpn", cpn_name,
                   "-r", role,
                   "-p", str(party_id)]

            result = self._run_cmd(cmd)
            result = json.loads(result)
            if "data" not in result:
                print ("job {}, component {} has no output metric".format(job_id, cpn_name))
                return
            return result["data"]
        except:
            print ("Can not get output model, err msg is {}".format(result))

