from __future__ import print_function

import unittest
import os
import requests
import time

from os import environ
import json
from deep_eq import deep_eq
import inspect
try:
    from ConfigParser import ConfigParser  # py2 @UnusedImport
except:
    from configparser import ConfigParser  # py3 @UnresolvedImport @Reimport

from biokbase.AbstractHandle.Client import AbstractHandle as HandleService  # @UnresolvedImport @IgnorePep8
from workspace.client import Workspace
from workspace.client import ServerError as WorkspaceError
from gaprice_convert_assy_file_to_contigs.gaprice_convert_assy_file_to_contigsImpl import gaprice_convert_assy_file_to_contigs  # @IgnorePep8
from gaprice_convert_assy_file_to_contigs.gaprice_convert_assy_file_to_contigsServer import MethodContext  # @IgnorePep8
from gaprice_convert_assy_file_to_contigs.baseclient import BaseClient

FILE_LOC = 'data'


class convert_assy_file_to_contigsTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.token = environ.get('KB_AUTH_TOKEN')
        cls.callbackURL = environ.get('SDK_CALLBACK_URL')
        print('CB URL: ' + cls.callbackURL)
        # WARNING: don't call any logging methods on the context object,
        # it'll result in a NoneType error
        cls.ctx = MethodContext(None)
        cls.ctx.update({'token': cls.token,
                        'provenance': [
                            {'service': 'gaprice_convert_assy_file_to_contigs',
                             'method': 'please_never_use_it_in_production',
                             'method_params': []
                             }],
                        'authenticated': 1})
        config_file = environ.get('KB_DEPLOYMENT_CONFIG', None)
        cls.cfg = {}
        config = ConfigParser()
        config.read(config_file)
        for nameval in config.items('gaprice_convert_assy_file_to_contigs'):
            cls.cfg[nameval[0]] = nameval[1]
        cls.wsURL = cls.cfg['workspace-url']
        cls.shockURL = cls.cfg['shock-url']
        cls.hs = HandleService(url=cls.cfg['handle-service-url'],
                               token=cls.token)
        cls.wsClient = Workspace(cls.wsURL, token=cls.token)
        wssuffix = int(time.time() * 1000)
        wsName = 'test_gaprice_convert_assy_file_to_contigs_' + str(wssuffix)
        cls.wsinfo = cls.wsClient.create_workspace({'workspace': wsName})
        print('created workspace ' + cls.getWsName())
        cls.serviceImpl = gaprice_convert_assy_file_to_contigs(cls.cfg)
        cls.staged = {}
        cls.nodes_to_delete = []
        cls.handles_to_delete = []
        cls.setupTestData()
        print('\n\n=============== Starting tests ==================')

    @classmethod
    def tearDownClass(cls):

        print('\n\n=============== Cleaning up ==================')

        if hasattr(cls, 'wsinfo'):
            cls.wsClient.delete_workspace({'workspace': cls.getWsName()})
            print('Test workspace was deleted: ' + cls.getWsName())
        if hasattr(cls, 'nodes_to_delete'):
            for node in cls.nodes_to_delete:
                cls.delete_shock_node(node)
        if hasattr(cls, 'handles_to_delete'):
            cls.hs.delete_handles(cls.hs.ids_to_handles(cls.handles_to_delete))
            print('Deleted handles ' + str(cls.handles_to_delete))

    @classmethod
    def getWsName(cls):
        return cls.wsinfo[1]

    def getImpl(self):
        return self.serviceImpl

    @classmethod
    def delete_shock_node(cls, node_id):
        header = {'Authorization': 'Oauth {0}'.format(cls.token)}
        requests.delete(cls.shockURL + '/node/' + node_id, headers=header,
                        allow_redirects=True)
        print('Deleted shock node ' + node_id)

    @classmethod
    def make_ref(self, object_info):
        return str(object_info[6]) + '/' + str(object_info[0]) + \
            '/' + str(object_info[4])

    # Helper script borrowed from the transform service, logger removed
    @classmethod
    def upload_file_to_shock(cls, file_path):
        """
        Use HTTP multi-part POST to save a file to a SHOCK instance.
        """

        header = dict()
        header["Authorization"] = "Oauth {0}".format(cls.token)

        if file_path is None:
            raise Exception("No file given for upload to SHOCK!")

        with open(os.path.abspath(file_path), 'rb') as dataFile:
            files = {'upload': dataFile}
            print('POSTing data')
            response = requests.post(
                cls.shockURL + '/node', headers=header, files=files,
                stream=True, allow_redirects=True)
            print('got response')

        if not response.ok:
            response.raise_for_status()

        result = response.json()

        if result['error']:
            raise Exception(result['error'][0])
        else:
            return result["data"]

    @classmethod
    def upload_file_to_shock_and_get_handle(cls, test_file):
        '''
        Uploads the file in test_file to shock and returns the node and a
        handle to the node.
        '''
        print('loading file to shock: ' + test_file)
        node = cls.upload_file_to_shock(test_file)
        cls.nodes_to_delete.append(node['id'])

        print('creating handle for shock id ' + node['id'])
        handle_id = cls.hs.persist_handle({'id': node['id'],
                                           'type': 'shock',
                                           'url': cls.shockURL
                                           })
        cls.handles_to_delete.append(handle_id)

        md5 = node['file']['checksum']['md5']
        return node['id'], handle_id, md5, node['file']['size']

    @classmethod
    def setupTestData(cls):
        cls.stage_assy_files()
        cls.stage_empty_data()

    @classmethod
    def stage_empty_data(cls):
        src_obj_name = 'empty'
        src_type = 'Empty.AType'

        objdata = cls.wsClient.save_objects(
            {'workspace': cls.getWsName(),
             'objects': [{'name': src_obj_name,
                          'type': src_type,
                          'data': {}}]
             })[0]
        cls.staged[src_obj_name] = {'obj_info': objdata,
                                    'ref': cls.make_ref(objdata)
                                    }

    @classmethod
    def stage_assy_files(cls):
        cls.load_assy_file_data(
            'sample.fa', 'AssemblyFile.json', 'test_assy_file', 'assy_file')
        cls.load_assy_file_data(
            'sample.fa', 'AssemblyFile.json',
            'test_assy_file_bad_node', 'assy_file_bad_node',
            with_bad_node_id=True)
        cls.load_assy_file_data(
            'sample_missing_data.fa',
            'AssemblyFile.json',
            'test_assy_file_missing_data', 'assy_file_missing_data')
        cls.load_assy_file_data(
            'sample_missing_data_last.fa',
            'AssemblyFile.json',
            'test_assy_file_missing_data_last', 'assy_file_missing_data_last')
        cls.load_assy_file_data(
            'sample_missing_data_ws.fa',
            'AssemblyFile.json',
            'test_assy_file_missing_data_ws', 'assy_file_missing_data_ws')
        cls.load_assy_file_data(
            'empty.fa',
            'AssemblyFile.json',
            'test_assy_file_empty', 'assy_file_empty')

    @classmethod
    def load_assy_file_data(cls, fa_file, ws_file, src_obj_name, key,
                            with_bad_node_id=False):
        src_type = 'KBaseFile.AssemblyFile'
        test_file = os.path.join(FILE_LOC, fa_file)
        node_id, handle, _, _ = cls.upload_file_to_shock_and_get_handle(
            test_file)
        if (with_bad_node_id):
            node_id += '1'

        test_json = os.path.join(FILE_LOC, ws_file)
        with open(test_json) as assyjsonfile:
            assyjson = json.loads(assyjsonfile.read())
        assyjson['assembly_file']['file']['url'] = cls.shockURL
        assyjson['assembly_file']['file']['id'] = node_id
        assyjson['assembly_file']['file']['hid'] = handle

        objdata = cls.wsClient.save_objects(
            {'workspace': cls.getWsName(),
             'objects': [{'name': src_obj_name,
                          'type': src_type,
                          'data': assyjson}]
             })[0]
        cls.staged[key] = {'obj_info': objdata,
                           'node': node_id,
                           'ref': cls.make_ref(objdata)}

    def test_assyfile_to_cs_basic_ops(self):
        print('*** running test test_assyfile_to_cs_basic _ops ***')
        staged = self.staged['assy_file']
        ref = staged['ref']
        bc = BaseClient(self.callbackURL)
        bc.call_method('CallbackServer.set_provenance',
                       [{'service': 'myserv',
                         'method': 'mymeth',
                         'service_ver': '0.0.2',
                         'method_params': ['foo', 'bar', 'baz'],
                         'input_ws_objects': [ref]
                         }]
                       )
        ret = self.getImpl().convert(
            self.ctx,
            {'workspace_name': self.getWsName(),
             'assembly_file': staged['obj_info'][1],
             'output_name': 'foobarbaz'
             })[0]

        report = self.wsClient.get_objects([{'ref': ret['report_ref']}])[0]

        self.assertEqual('KBaseReport.Report', report['info'][2].split('-')[0])
        self.assertEqual(1, len(report['data']['objects_created']))
        self.assertEqual('Assembled contigs',
                         report['data']['objects_created'][0]['description'])
        self.assertIn('Assembled into 4 contigs',
                      report['data']['text_message'])

        cs_ref = report['data']['objects_created'][0]['ref']
        cs = self.wsClient.get_objects([{'ref': cs_ref}])[0]
        self.assertEqual('KBaseGenomes.ContigSet', cs['info'][2].split('-')[0])

        rep_prov = report['provenance']
        cs_prov = cs['provenance']
        self.assertEqual(len(rep_prov), 1)
        self.assertEqual(len(cs_prov), 1)
        rep_prov = rep_prov[0]
        cs_prov = cs_prov[0]
        for p in [rep_prov, cs_prov]:
            self.assertEqual(p['service'], 'myserv')
            self.assertEqual(p['method'], 'mymeth')
            self.assertEqual(p['service_ver'], '0.0.2')
            self.assertEqual(p['method_params'], ['foo', 'bar', 'baz'])
            self.assertEqual(p['input_ws_objects'], [ref])
            self.assertEqual(p['resolved_ws_objects'], [ref])
            sa = p['subactions']
            self.assertEqual(len(sa), 0)
            # don't check ver or commit since they can change from run to run

        with open(os.path.join(FILE_LOC, 'ContigSetOut.json')) as f:
            expected = json.loads(f.read())
        expected['fasta_ref'] = staged['node']
        deep_eq(expected, cs['data'], _assert=True)

    def test_no_ws(self):
        err = 'workspace_name must be provided in params'
        self.run_error(None, 'foo', 'foo', err)
        self.run_error('', 'foo', 'foo', err)

    def test_missing_ws(self):
        err = ('Object foo cannot be accessed: No workspace with name ' +
               'Ireallyhopethiswsdoesntexist exists')
        self.run_error('Ireallyhopethiswsdoesntexist', 'foo', 'foo', err,
                       exception=WorkspaceError)

    def test_no_obj(self):
        err = 'assembly_file must be provided in params'
        self.run_error(self.getWsName(), None, 'foo', err)
        self.run_error(self.getWsName(), '', 'foo', err)

    def test_missing_obj(self):
        err = ('No object with name Ireallyhopethisobjdoesntexist exists in ' +
               'workspace ' + str(self.wsinfo[0]) + ' (name ' + self.wsinfo[1] + ')')
        self.run_error(self.getWsName(), 'Ireallyhopethisobjdoesntexist',
                       'foo', err, exception=WorkspaceError)

    def test_no_output(self):
        err = 'output_name must be provided in params'
        self.run_error(self.getWsName(), 'foo', None, err)
        self.run_error(self.getWsName(), 'foo', '', err)

    def test_bad_output_name(self):
        err = 'Object 1: Illegal character in object name bad*name: *'
        self.run_error(self.getWsName(), 'test_assy_file', 'bad*name', err,
                       exception=WorkspaceError)

    def test_bad_type(self):
        err = 'This method only works on the KBaseFile.AssemblyFile type'
        self.run_error(self.getWsName(), 'empty', 'foo', err)

    def test_missing_data(self):
        err = 'There is no sequence related to FASTA record: id2 desc2'
        self.run_error(self.getWsName(), 'test_assy_file_missing_data', 'foo',
                       err)

    def test_missing_data_last(self):
        err = 'There is no sequence related to FASTA record: id4 desc4'
        self.run_error(self.getWsName(), 'test_assy_file_missing_data_last',
                       'foo', err)

    def test_missing_data_whitespace(self):
        err = 'There is no sequence related to FASTA record: id3 desc3'
        self.run_error(self.getWsName(), 'test_assy_file_missing_data_ws',
                       'foo', err)

    def test_empty_file(self):
        err = 'There are no contigs in this file'
        self.run_error(self.getWsName(), 'test_assy_file_empty', 'foo', err)

    def test_bad_shock_node(self):
        err = 'Node not found'
        self.run_error(self.getWsName(), 'test_assy_file_bad_node', 'foo', err)

    def run_error(self, workspace, obj, output, error, exception=ValueError):

        test_name = inspect.stack()[1][3]
        print('\n***** starting expected fail test: ' + test_name + ' *****')

        with self.assertRaises(exception) as context:
            self.getImpl().convert(
                self.ctx,
                {'workspace_name': workspace,
                 'assembly_file': obj,
                 'output_name': output
                 })
        self.assertEqual(error, str(context.exception.message))
