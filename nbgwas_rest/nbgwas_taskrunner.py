#!/usr/bin/env python


import os
import sys
import argparse
import logging
import time
import shutil
import json

import nbgwas
from nbgwas import Nbgwas

import nbgwas_rest
import pandas as pd
import networkx as nx
from ndex2 import create_nice_cx_from_server



logger = logging.getLogger('nbgwas_taskrunner')

LOG_FORMAT = "%(asctime)-15s %(levelname)s %(relativeCreated)dms " \
             "%(filename)s::%(funcName)s():%(lineno)d %(message)s"


def _parse_arguments(desc, args):
    """Parses command line arguments"""
    help_formatter = argparse.RawDescriptionHelpFormatter
    parser = argparse.ArgumentParser(description=desc,
                                     formatter_class=help_formatter)
    parser.add_argument('taskdir', help='Base directory where tasks'
                                        'are located')
    parser.add_argument('--wait_time', type=int, default=30,
                        help='Time in seconds to wait'
                             'before looking for new'
                             'tasks')
    parser.add_argument('--version', action='version',
                        version=('%(prog)s ' + nbgwas_rest.__version__))
    parser.add_argument('--verbose', '-v', action='count',
                        help='Increases logging verbosity, max is 4',
                        default=1)
    return parser.parse_args(args)


def _setuplogging(theargs):
    """Sets up logging"""
    level = (50 - (10 * theargs.verbose))
    logging.basicConfig(format=LOG_FORMAT,
                        level=level)
    for k in logging.Logger.manager.loggerDict.keys():
        thelog = logging.Logger.manager.loggerDict[k]

        # not sure if this is the cleanest way to do this
        # but the dictionary of Loggers has a PlaceHolder
        # object which tosses an exception if setLevel()
        # is called so I'm checking the class names
        try:
            thelog.setLevel(level)
        except AttributeError:
            pass


class FileBasedTask(object):
    """Represents a task
    """
    def __init__(self, taskdir, taskdict):
        self._taskdir = taskdir
        self._taskdict = taskdict
        self._networkx_obj = None
        self._genelevelsummary = None
        self._filteredseedlist = None
        self._resultdata = None

    def save_task(self):
        """
        Updates task in datastore. For filesystem based
        task this means rewriting the task.json file
        :return: None for success otherwise string containing error message
        """
        if self._taskdir is None:
            return 'Task dir is None'

        tjsonfile = os.path.join(self._taskdir, nbgwas_rest.TASK_JSON)
        logger.debug('Writing task data to: ' + tjsonfile)
        with open(tjsonfile, 'w') as f:
            json.dump(self._taskdict, f)

        if self._resultdata is not None:
            resultfile = os.path.join(self._taskdir, nbgwas_rest.RESULT)
            logger.debug('Writing result data to: ' + resultfile)
            with open(resultfile, 'w') as f:
                json.dump(self._resultdata, f)
                f.flush()
        return None

    def move_task(self, new_state,
                  error_message=None):
        """
        Changes state of task to new_state
        :param new_state: new state
        :return: None
        """
        taskattrib = self._get_uuid_ip_state_basedir_from_path()
        if taskattrib is None or taskattrib['basedir'] is None:
            return 'Unable to extract state basedir from task path'

        if taskattrib['state'] == new_state:
            logger.debug('Attempt to move task to same state: ' +
                         self._taskdir)
            return None

        # if new state is error still put the task into
        # done directory, but update error message in
        # task json
        if new_state == nbgwas_rest.ERROR_STATUS:
            new_state = nbgwas_rest.DONE_STATUS

            if error_message is None:
                emsg = 'Unknown error'
            else:
                emsg = error_message
            logger.info('Task set to error state with message: ' +
                        emsg)
            self._taskdict[nbgwas_rest.ERROR_PARAM] = emsg
            self.save_task()
        logger.debug('Changing task: ' + str(taskattrib['uuid']) + ' to state ' +
                     new_state)
        ptaskdir = os.path.join(taskattrib['basedir'], new_state,
                                taskattrib['ipaddr'], taskattrib['uuid'])
        shutil.move(self._taskdir, ptaskdir)
        self._taskdir = ptaskdir
        return None

    def _get_uuid_ip_state_basedir_from_path(self):
        """
        Parses taskdir path into main parts and returns
        result as tuple
        :return: {'basedir': basedir,
                  'state': state
                  'ipaddr': ip address,
                  'uuid': task uuid}
        """
        if self._taskdir is None:
            logger.error('Task dir not set')
            return {'basedir': None,
                    'state': None,
                    'ipaddr': None,
                    'uuid': None}
        taskuuid = os.path.basename(self._taskdir)
        ipdir = os.path.dirname(self._taskdir)
        ipaddr = os.path.basename(ipdir)
        statedir = os.path.dirname(ipdir)
        state = os.path.basename(statedir)
        basedir = os.path.dirname(statedir)
        return {'basedir': basedir,
                'state': state,
                'ipaddr': ipaddr,
                'uuid': taskuuid}

    def get_ipaddress(self):
        """
        gets ip address
        :return:
        """
        return self._get_uuid_ip_state_basedir_from_path()['ipaddr']

    def get_state(self):
        """
        Gets current state of task based on taskdir
        :return:
        """
        return self._get_uuid_ip_state_basedir_from_path()['state']

    def get_task_uuid(self):
        """
        Parses taskdir path to get uuid
        :return: string containing uuid or None if not found
        """
        return self._get_uuid_ip_state_basedir_from_path()['uuid']

    def get_task_summary_as_str(self):
        """
        Prints quick summary of task
        :return:
        """
        res = self._get_uuid_ip_state_basedir_from_path()
        return str(res)

    def set_result_data(self, result):
        """
        Sets result data object
        :param result:
        :return:
        """
        self._resultdata = result

    def set_networkx_object(self, networkx_obj):
        """
        Sets networkx_obj
        :param networkx_obj:
        :return:
        """
        self._networkx_obj = networkx_obj

    def get_networkx_object(self):
        """
        Gets networkx_obj
        :return:
        """
        return self._networkx_obj

    def set_gene_level_summary(self, gls):
        """
        Sets gene list summary obj
        :param gls:
        :return:
        """
        self._genelevelsummary = gls

    def get_gene_level_summary(self):
        """
        Gets gene list summary
        :return:
        """
        return self._genelevelsummary

    def set_filtered_seed_list(self, seedlist):
        """
        sets filtered seed list
        :param seedlist:
        :return:
        """
        self._filteredseedlist = seedlist

    def get_filtered_seed_list(self):
        """
        Gets filtered seed list
        :return:
        """
        return self._filteredseedlist

    def set_taskdir(self, taskdir):
        self._taskdir = taskdir

    def get_taskdir(self):
        return self._taskdir

    def set_taskdict(self, taskdict):
        self._taskdict = taskdict

    def get_taskdict(self):
        return self._taskdict

    def get_ipaddress(self):
        """
        Gets ip address
        :return:
        """
        return self._taskdict[nbgwas_rest.REMOTEIP_PARAM]

    def get_alpha(self):
        return self._taskdict[nbgwas_rest.ALPHA_PARAM]

    def get_seeds(self):
        return self._taskdict[nbgwas_rest.SEEDS_PARAM]

    def get_bigim(self):
        if nbgwas_rest.COLUMN_PARAM not in self._taskdict:
            return None
        return self._taskdict[nbgwas_rest.COLUMN_PARAM]

    def get_ndex(self):
        if nbgwas_rest.NDEX_PARAM not in self._taskdict:
            return None
        return self._taskdict[nbgwas_rest.NDEX_PARAM]

    def get_network(self):
        if self._taskdir is None:
            return None
        network_dfile = os.path.join(self._taskdir,
                                     nbgwas_rest.NETWORK_DATA)
        if not os.path.isfile(network_dfile):
            return None
        return network_dfile


class FileBasedSubmittedTaskFactory(object):
    """
    Reads file system to get tasks
    """
    def __init__(self, taskdir):
        self._taskdir = taskdir
        self._submitdir = os.path.join(self._taskdir,
                                       nbgwas_rest.SUBMITTED_STATUS)
        self._problemlist = []

    def get_next_task(self):
        """
        Looks for next task in task dir. currently finds the first
        :return:
        """
        if self._submitdir is None:
            logger.error('Submit directory is None')
            return None
        if not os.path.isdir(self._submitdir):
            logger.error(self._submitdir +
                         ' does not exist or is not a directory')
            return None
        for entry in os.listdir(self._submitdir):
            fp = os.path.join(self._submitdir, entry)
            if not os.path.isdir(fp):
                continue
            for subentry in os.listdir(fp):
                subfp = os.path.join(fp, subentry)
                if os.path.isdir(subfp):
                    tjson = os.path.join(subfp, nbgwas_rest.TASK_JSON)
                    if os.path.isfile(tjson):
                        try:
                            with open(tjson, 'r') as f:
                                jsondata = json.load(f)
                            return FileBasedTask(subfp, jsondata)
                        except Exception as e:
                            if subfp not in self._problemlist:
                                logger.info('Skipping task: ' + subfp +
                                            ' due to error reading json' +
                                            ' file: ' + str(e))
                                self._problemlist.append(subfp)
        return None

    def clean_up_problem_list(self):
        """
        Iterate through problem tasks and move to done state
        :return:
        """
        logger.debug('Cleaning up problem ' + str(len(self._problemlist)) +
                     ' tasks')
        emsg='Unknown error with task'
        for entry in self._problemlist:
            t = FileBasedTask(entry, {})
            t.move_task(nbgwas_rest.ERROR_STATUS, error_message=emsg)
            self._problemlist.remove(entry)

    def get_size_of_problem_list(self):
        """
        Gets size of problem list
        :return:
        """
        return len(self._problemlist)

class NbgwasTaskRunner(object):
    """
    Runs tasks created by Nbgwas REST service
    """

    SIF_GENE_ONE = 'Gene1'
    SIF_GENE_TWO = 'Gene2'
    SIF_VAL = 'Val'
    SIF_NAMES = [SIF_GENE_ONE, SIF_GENE_TWO, SIF_VAL]
    NDEX_NAME = 'name'

    def __init__(self, wait_time=30,
                 taskfactory=None,
                 processor=None,
                 ndex_server='public.ndexbio.org'):
        self._taskfactory = taskfactory
        self._wait_time = wait_time
        self._ndex_server = ndex_server

    def _get_networkx_object(self, task):
        """
        Examines task and generates appropriate
        networkx object that is returned
        :param task:
        :return: same task object
        """
        if task is None:
            logger.error('task is None')
            return None

        sif_file = task.get_network()
        if sif_file is not None:
            return self._get_networkx_object_from_sif_file(sif_file)

        ndex_id = task.get_ndex()
        if ndex_id is not None:
            return self._get_networkx_object_from_ndex(ndex_id)

        return None

    def _get_networkx_object_from_sif_file(self, sif_file):
        """
        Create networkx object appropriate for nbgwas
        from sif file stored in task directory
        :param sif_file: Path to sif file
        :return: networkx object upon success or None for failure
        """
        if not os.path.isfile(sif_file):
            return None
        with open(sif_file, 'r') as f:
            network_df = pd.read_csv(f, sep='\t',
                                     names=NbgwasTaskRunner.SIF_NAMES)

        return nx.from_pandas_dataframe(network_df,
                                        NbgwasTaskRunner.SIF_GENE_ONE,
                                        NbgwasTaskRunner.SIF_GENE_TWO)

    def _get_networkx_object_from_ndex(self, ndex_id):
        """
        Extracts networkx object from ndex
        :param task: contains id to get
        :return:
        """
        cxnet = create_nice_cx_from_server(server=self._ndex_server,
                                           uuid=ndex_id)
        dG = cxnet.to_networkx()
        name_map = {i: j[NbgwasTaskRunner.NDEX_NAME]
                    for i, j in dG.node.items()}
        return nx.relabel_nodes(dG, name_map)

    def _get_seeds(self, task):
        """
        Parse seeds and verify they exist in network
        :param seedstr:
        :param networkx_obj:
        :return:
        """
        if task.get_seeds() is None:
            return None
        slist = task.get_seeds().split(',')
        for s in slist:
            if s not in task.get_networkx_object().nodes():
                slist.remove(s)
                logger.info(s + ' seed not in nodes')
        if len(slist) is 0:
            logger.error('No seeds left after checking them against'
                         'network')
            return None
        return slist

    def _create_gene_level_summary(self, task):
        """

        :param genes:
        :param seeds:
        :return:
        """
        gls = pd.DataFrame([task.get_networkx_object().nodes()],
                           index=['Genes']).T
        gls['p-value'] = 1
        gls.loc[gls['Genes'].isin(task.get_filtered_seed_list()),
                'p-value'] = 0
        return gls

    def _process_task(self, task):
        """
        Processes a task
        :param taskdir:
        :return:
        """
        logger.info('Task dir: ' + task.get_taskdir())
        task.move_task(nbgwas_rest.PROCESSING_STATUS)

        n_obj = self._get_networkx_object(task)
        if n_obj is None:
            emsg = 'Unable to get networkx object for task'
            logger.error(emsg)
            task.move_task(nbgwas_rest.ERROR_STATUS,
                           error_message=emsg)
            return
        task.set_networkx_object(n_obj)

        seed_list = self._get_seeds(task)
        if seed_list is None or len(seed_list) is 0:
            emsg = 'No seeds are in network'
            logger.error(emsg)
            task.move_task(nbgwas_rest.ERROR_STATUS,
                           error_message=emsg)
            return
        task.set_filtered_seed_list(seed_list)

        gls = self._create_gene_level_summary(task)
        if gls is None:
            emsg = 'Unable to create gene level summary'
            logger.error(emsg)
            task.move_task(nbgwas_rest.ERROR_STATUS,
                           error_message=emsg)
            return
        task.set_gene_level_summary(gls)

        result = self._run_nbgwas(task)
        if result is None:
            emsg = 'No result generated'
            logger.error(emsg)
            task.move_task(nbgwas_rest.ERROR_STATUS,
                           error_message=emsg)
            return
        logger.info('Task processing completed')
        task.set_result_data(result)
        task.save_task()
        task.move_task(nbgwas_rest.DONE_STATUS)
        return

    def _run_nbgwas(self, task):
        """
        Runs nbgwas processing
        :param task:
        :return:
        """
        g = Nbgwas(
            gene_level_summary=task.get_gene_level_summary(),
            gene_col='Genes',
            gene_pval_col='p-value',
            network=task.get_networkx_object(),
        )

        g.convert_to_heat()
        g.diffuse(method='random_walk', alpha=task.get_alpha())
        return json.loads(g.heat.iloc[:, -1].to_json())

    def run_tasks(self):
        """
        Main entry point, this function loops looking for
        tasks to run.
        :return:
        """
        cleanupcounter = 0
        while True:
            task = self._taskfactory.get_next_task()
            if task is None:
                if self._taskfactory.get_size_of_problem_list() > 0:
                    cleanupcounter = cleanupcounter + 1
                    if cleanupcounter >= 3:
                        self._taskfactory.clean_up_problem_list()
                        cleanupcounter = 0
                    else:
                        time.sleep(self._wait_time)
                else:
                    time.sleep(self._wait_time)

                continue
            logger.debug('Found a task: ' + str(task.get_taskdir()))
            try:
                self._process_task(task)
            except Exception as e:
                emsg = ('Caught exception processing task: ' +
                        task.get_taskdir() + ' : ' + str(e))
                logger.exception('Skipping task cause - ' + emsg)
                task.move_task(nbgwas_rest.ERROR_STATUS,
                               error_message=emsg)


def main(args):
    """Main entry point"""
    desc = """Runs tasks generated by NBGWAS REST service

    """
    theargs = _parse_arguments(desc, args[1:])
    theargs.program = args[0]
    theargs.version = nbgwas_rest.__version__
    _setuplogging(theargs)
    try:
        ab_tdir = os.path.abspath(theargs.taskdir)
        logger.debug('Task directory set to: ' + ab_tdir)

        tfac = FileBasedSubmittedTaskFactory(ab_tdir)
        runner = NbgwasTaskRunner(taskfactory=tfac,
                                  wait_time=theargs.wait_time)
        runner.run_tasks()
    except Exception as e:
        logger.exception("Error caught exception")
        return 2
    finally:
        logging.shutdown()


if __name__ == '__main__':  # pragma: no cover
    sys.exit(main(sys.argv))