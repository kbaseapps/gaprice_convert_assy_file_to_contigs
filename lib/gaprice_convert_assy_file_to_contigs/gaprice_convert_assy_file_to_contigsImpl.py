#BEGIN_HEADER
import hashlib
import os
import re
import requests
import json
from workspace.client import Workspace
import uuid
import numpy as np
#END_HEADER


class gaprice_convert_assy_file_to_contigs:
    '''
    Module Name:
    gaprice_convert_assy_file_to_contigs

    Module Description:
    A KBase module: convert_assy_file_to_contigs
    '''

    ######## WARNING FOR GEVENT USERS #######
    # Since asynchronous IO can lead to methods - even the same method -
    # interrupting each other, you must be *very* careful when using global
    # state. A method could easily clobber the state set by another while
    # the latter method is running.
    #########################################
    VERSION = "0.0.1"
    GIT_URL = ""
    GIT_COMMIT_HASH = "54117b5b1793d90adf935f2982f367f5c0ddaf40"
    
    #BEGIN_CLASS_HEADER

    URL_WS = 'workspace-url'
    URL_SHOCK = 'shock-url'

    def download_workspace_data(self, source_ws, source_obj, token):

        ws = Workspace(self.workspaceURL, token=token)
        objdata = ws.get_objects(
            [{'ref': source_ws + '/' + source_obj}])[0]
        info = objdata['info']
        if info[2].split('-')[0] != 'KBaseFile.AssemblyFile':
            raise ValueError(
                'This method only works on the KBaseFile.AssemblyFile type')
        shock_url = objdata['data']['assembly_file']['file']['url']
        shock_id = objdata['data']['assembly_file']['file']['id']
        source = objdata['data'].get('source')

        outfile = os.path.join(self.scratch, source_obj)
        shock_node = shock_url + '/node/' + shock_id + '/?download'
        headers = {'Authorization': 'OAuth ' + token}
        with open(outfile, 'w') as f:
            response = requests.get(shock_node, stream=True, headers=headers)
            if not response.ok:
                try:
                    err = json.loads(response.content)['error'][0]
                except:
                    print("Couldn't parse response error content: " +
                          response.content)
                    response.raise_for_status()
                raise ValueError(str(err))
            for block in response.iter_content(1024):
                if not block:
                    break
                f.write(block)

        return info[6], shock_id, source

    # adapted from
    # https://github.com/kbase/transform/blob/master/plugins/scripts/convert/trns_transform_KBaseFile_AssemblyFile_to_KBaseGenomes_ContigSet.py
    # which was adapted from an early version of
    # https://github.com/kbase/transform/blob/master/plugins/scripts/upload/trns_transform_FASTA_DNA_Assembly_to_KBaseGenomes_ContigSet.py
    def convert_to_contigs(self, input_file_name, source, contigset_id,
                           shock_id):
        """
        Converts fasta to KBaseGenomes.ContigSet and saves to WS.
        Note the MD5 for the contig is generated by uppercasing the sequence.
        The ContigSet MD5 is generated by taking the MD5 of joining the sorted
        list of individual contig's MD5s with a comma separator
        Args:
            input_file_name: A file name for the input FASTA data.
            contigset_id: The id of the ContigSet. If not
                specified the name will default to the name of the input file
                appended with "_contig_set"'
            shock_id: Shock id for the fasta file if it already exists in shock
        """

        print('Starting conversion of FASTA to KBaseGenomes.ContigSet')

        print('Building Object.')

        if not os.path.isfile(input_file_name):
            raise ValueError('The input file name {0} is not a file!'.format(
                input_file_name))

        # default if not too large
        contig_set_has_sequences = True

        fasta_filesize = os.stat(input_file_name).st_size
        if fasta_filesize > 900000000:
            # Fasta file too large to save sequences into the ContigSet object.
            print(
                'The FASTA input file is too large to fit in the workspace. ' +
                'A ContigSet object will be created without sequences, but ' +
                'will contain a reference to the file.')
            contig_set_has_sequences = False

        with open(input_file_name, 'r') as input_file_handle:
            fasta_header = None
            sequence_list = []
            fasta_dict = dict()
            first_header_found = False
            contig_set_md5_list = []
            # Pattern for replacing white space
            pattern = re.compile(r'\s+')
            for current_line in input_file_handle:
                if (current_line[0] == '>'):
                    # found a header line
                    # Wrap up previous fasta sequence
                    if (not sequence_list) and first_header_found:
                        raise ValueError(
                            'There is no sequence related to FASTA record: {0}'
                            .format(fasta_header))
                    if not first_header_found:
                        first_header_found = True
                    else:
                        # build up sequence and remove all white space
                        total_sequence = ''.join(sequence_list)
                        total_sequence = re.sub(pattern, '', total_sequence)
                        if not total_sequence:
                            raise ValueError(
                                'There is no sequence related to FASTA ' +
                                'record: ' + fasta_header)
                        try:
                            fasta_key, fasta_description = \
                                fasta_header.strip().split(' ', 1)
                        except:
                            fasta_key = fasta_header.strip()
                            fasta_description = None
                        contig_dict = dict()
                        contig_dict['id'] = fasta_key
                        contig_dict['length'] = len(total_sequence)
                        contig_dict['name'] = fasta_key
                        md5wrds = 'Note MD5 is generated from uppercasing ' + \
                            'the sequence'
                        if fasta_description:
                            fasta_description += '. ' + md5wrds
                        else:
                            fasta_description = md5wrds
                        contig_dict['description'] = fasta_description
                        contig_md5 = hashlib.md5(
                            total_sequence.upper()).hexdigest()
                        contig_dict['md5'] = contig_md5
                        contig_set_md5_list.append(contig_md5)
                        if contig_set_has_sequences:
                            contig_dict['sequence'] = total_sequence
                        else:
                            contig_dict['sequence'] = None
                        fasta_dict[fasta_header] = contig_dict

                        # get set up for next fasta sequence
                        sequence_list = []
                    fasta_header = current_line.replace('>', '').strip()
                else:
                    sequence_list.append(current_line)

        # wrap up last fasta sequence, should really make this a method
        if (not sequence_list) and first_header_found:
            raise ValueError(
                "There is no sequence related to FASTA record: {0}".format(
                    fasta_header))
        elif not first_header_found:
            raise ValueError("There are no contigs in this file")
        else:
            # build up sequence and remove all white space
            total_sequence = ''.join(sequence_list)
            total_sequence = re.sub(pattern, '', total_sequence)
            if not total_sequence:
                raise ValueError(
                    "There is no sequence related to FASTA record: " +
                    fasta_header)
            try:
                fasta_key, fasta_description = \
                    fasta_header.strip().split(' ', 1)
            except:
                fasta_key = fasta_header.strip()
                fasta_description = None
            contig_dict = dict()
            contig_dict['id'] = fasta_key
            contig_dict['length'] = len(total_sequence)
            contig_dict['name'] = fasta_key
            md5wrds = 'Note MD5 is generated from uppercasing ' + \
                'the sequence'
            if fasta_description:
                fasta_description += '. ' + md5wrds
            else:
                fasta_description = md5wrds
            contig_dict['description'] = fasta_description
            contig_md5 = hashlib.md5(total_sequence.upper()).hexdigest()
            contig_dict['md5'] = contig_md5
            contig_set_md5_list.append(contig_md5)
            if contig_set_has_sequences:
                contig_dict['sequence'] = total_sequence
            else:
                contig_dict['sequence'] = None
            fasta_dict[fasta_header] = contig_dict

        contig_set_dict = dict()
        # joining by commas is goofy, but keep consistency with the uploader
        contig_set_dict['md5'] = hashlib.md5(','.join(sorted(
            contig_set_md5_list))).hexdigest()
        contig_set_dict['id'] = contigset_id
        contig_set_dict['name'] = contigset_id
        s = 'unknown'
        if source and source['source']:
            s = source['source']
        contig_set_dict['source'] = s
        sid = os.path.basename(input_file_name)
        if source and source['source_id']:
            sid = source['source_id']
        contig_set_dict['source_id'] = sid
        contig_set_dict['contigs'] = [fasta_dict[x] for x in sorted(
            fasta_dict.keys())]

        contig_set_dict['fasta_ref'] = shock_id

        print('Conversion completed.')
        return contig_set_dict

    def load_report(self, contigset, cs_ref, wscli, wsn, wsid, output,
                    provenance):
        lengths = [contig['length'] for contig in contigset['contigs']]

        report = ''
        report += 'ContigSet saved to: ' + wsn + '/' + output + '\n'
        report += 'Assembled into ' + str(len(lengths)) + ' contigs.\n'
        report += 'Avg Length: ' + str(sum(lengths) / float(len(lengths))) + \
            ' bp.\n'

        # compute a simple contig length distribution
        bins = 10
        counts, edges = np.histogram(lengths, bins)  # @UndefinedVariable
        report += 'Contig Length Distribution (# of contigs -- min to max ' +\
            'basepairs):\n'
        for c in range(bins):
            report += '   ' + str(counts[c]) + '\t--\t' + str(edges[c]) +\
                ' to ' + str(edges[c + 1]) + ' bp\n'

        reportObj = {
            'objects_created': [{'ref': cs_ref,
                                 'description': 'Assembled contigs'}],
            'text_message': report
        }

        reportName = 'convert_report_' + str(uuid.uuid4())
        report_obj_info = wscli.save_objects({
                'id': wsid,
                'objects': [
                    {
                        'type': 'KBaseReport.Report',
                        'data': reportObj,
                        'name': reportName,
                        'hidden': 1,
                        'provenance': provenance
                    }
                ]
            })[0]
        reportRef = self.make_ref(report_obj_info)
        return reportName, reportRef

    def make_ref(self, object_info):
        return str(object_info[6]) + '/' + str(object_info[0]) + \
            '/' + str(object_info[4])

    #END_CLASS_HEADER

    # config contains contents of config file in a hash or None if it couldn't
    # be found
    def __init__(self, config):
        #BEGIN_CONSTRUCTOR
        self.workspaceURL = config[self.URL_WS]
        self.shockURL = config[self.URL_SHOCK]
        self.scratch = os.path.abspath(config['scratch'])
        if not os.path.exists(self.scratch):
            os.makedirs(self.scratch)
        #END_CONSTRUCTOR
        pass
    

    def convert(self, ctx, params):
        """
        :param params: instance of type "ConvertParams" (Input parameters for
           the conversion function. string workspace_name - the name of the
           workspace from which to take input and store output. string
           assembly_file - the name of the input KBaseFile.AssemblyFile to
           convert to a ContigSet. string output_name - the name for the
           produced ContigSet.) -> structure: parameter "workspace_name" of
           String, parameter "assembly_file" of String, parameter
           "output_name" of String
        :returns: instance of type "ConvertOutput" (Output parameters the
           conversion. string report_name - the name of the
           KBaseReport.Report workspace object. string report_ref - the
           workspace reference of the report.) -> structure: parameter
           "report_name" of String, parameter "report_ref" of String
        """
        # ctx is the context object
        # return variables are: output
        #BEGIN convert

        ''' this whole thing should get rewritten, looking at reads->file,
        spades, & Jason's CS uploader for best practices'''

        wsn = params.get('workspace_name')
        if not wsn:
            raise ValueError('workspace_name must be provided in params')
        input_ = params.get('assembly_file')
        if not input_:
            raise ValueError('assembly_file must be provided in params')
        output = params.get('output_name')
        if not output:
            raise ValueError('output_name must be provided in params')
        token = ctx.get('token')
        if not token:
            raise ValueError('no token in context object')
        wsid, shock_id, source = self.download_workspace_data(
            wsn, input_, token)
        inputfile = os.path.join(self.scratch, input_)

        cs = self.convert_to_contigs(inputfile, source, output, shock_id)

        ws = Workspace(self.workspaceURL, token=token)
        new_obj_info = ws.save_objects({
                'id': wsid,
                'objects': [
                    {
                        'type': 'KBaseGenomes.ContigSet',
                        'data': cs,
                        'name': output,
                        'provenance': ctx.provenance()
                    }
                ]
            })[0]
        cs_ref = self.make_ref(new_obj_info)

        report_name, report_ref = self.load_report(
            cs, cs_ref, ws, wsn, wsid, output, ctx.provenance())

        output = {'report_name': report_name,
                  'report_ref': report_ref
                  }

        #END convert

        # At some point might do deeper type checking...
        if not isinstance(output, dict):
            raise ValueError('Method convert return value ' +
                             'output is not type dict as required.')
        # return the results
        return [output]

    def status(self, ctx):
        #BEGIN_STATUS
        returnVal = {'state': "OK", 'message': "",
                     'version': self.VERSION,
                     'git_url': self.GIT_URL,
                     'git_commit_hash': self.GIT_COMMIT_HASH}
        del ctx
        #END_STATUS
        return [returnVal]
