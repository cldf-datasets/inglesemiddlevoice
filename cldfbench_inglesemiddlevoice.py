import pathlib
import re
import unicodedata
import sys
from collections import defaultdict
from itertools import chain

from cldfbench import CLDFSpec, Dataset as BaseDataset
from simplepybtex.database import parse_file


ID_CHARS = (
    'abcdefghijklmnopqrstuvwxyz'
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    '0123456789-_')


def slug(s):
    return ''.join(
        c
        for c in unicodedata.normalize('NFKD', s).lower()
        if c in ID_CHARS)


def read_parameters(csv_rows):
    return {
        row['Original_Name']: {
            'ID': slug(row['Name']),
            'Name': row['Name'],
            'Description': row['Description'],
        }
        for row in csv_rows}


def read_ccodes(csv_rows, cparameters, lparameters):
    parameter_ids = {
        original_name: param['ID']
        for original_name, param in chain(cparameters.items(), lparameters.items())}
    return {
        (row['Original_Parameter_Name'], row['Original_Name']):
        {
            'ID': row['ID'],
            'Parameter_ID': parameter_ids[row['Original_Parameter_Name']],
            'Name': row['Name'],
            'Map_Icon': row.get('Map_Icon') or '',
        }
        for row in csv_rows}


def fix_glottocode(glottocode):
    fixes = {
        'faas1245': 'fass1245',
        'sand1237': 'sand1273',
    }
    return fixes.get(glottocode) or glottocode


def make_languages(data, glottolog):
    glottocodes = {
        fix_glottocode(row['Glottocode']): row['Language']
        for row in data}
    languoids = {lg.id: lg for lg in glottolog.languoids(ids=glottocodes)}
    return [
        {
            'ID': (lg := languoids[glottocode]).id,
            'Name': name,
            'Glottocode': lg.id,
            'ISO639P3code': lg.iso_code,
            'Macroarea': lg.macroareas[0].name if lg.macroareas else '',
            'Latitude': lg.latitude,
            'Longitude': lg.longitude,
        }
        for glottocode, name in sorted(glottocodes.items())]


def valid_marker_citation(ref, sources, gc, marker):
    bibkey = ref.split('[')[0]
    if bibkey in sources:
        return True
    else:
        print(f'{gc} ({marker}): Unknown bibkey: {bibkey}', file=sys.stderr)
        return False


def make_markers(data, sources):
    markers = {
        ((gc := fix_glottocode(row['Glottocode'])), row['Middle marker']): {
            'ID': '{}-{}'.format(gc, slug(row['Middle marker'])),
            'Language_ID': gc,
            'Name': row['Middle marker'],
            'Source': [
                citation
                for citation in re.split(r'\s*;\s*', row['References'])
                if valid_marker_citation(citation, sources, gc, row['Middle marker'])]
        }
        for row in data}
    assert len(markers) == len(data), 'markers are unique'
    return markers


def make_marker_values(data, markers, cparameters, codes):
    return [
        {
            'Parameter_ID': (param_id := param['ID']),
            'Construction_ID': (construction_id := markers[
                fix_glottocode(row['Glottocode']), row['Middle marker']]['ID']),
            'Code_ID': (code := codes[param_col, value])['ID'],
            'Value': code['Name'],
            'ID': f'{construction_id}-{param_id}',
        }
        for row in data
        for param_col, param in cparameters.items()
        if (value := row.get(param_col)) and value != '_']


def make_lvalues(data, lparameters, codes):
    lvalues = {}
    for row in data:
        for param_col, param in lparameters.items():
            if (value := row.get(param_col)) and value != '_':
                param_id = param['ID']
                lang_id = fix_glottocode(row['Glottocode'])
                code = codes[param_col, value]
                if (previous_value := lvalues.get((lang_id, param_id))):
                    # double check that all values are the same
                    assert previous_value['Code_ID'] == code['ID']
                else:
                    lvalues[lang_id, param_id] = {
                        'ID': f'{lang_id}-{param_id}',
                        'Language_ID': lang_id,
                        'Parameter_ID': param_id,
                        'Code_ID': code['ID'],
                        'Value': code['Name'],
                    }
    return list(lvalues.values())


def iter_aggregated_markers(data):
    aggregated_markers = defaultdict(list)
    for row in data:
        aggregated_markers[fix_glottocode(row['Glottocode'])].append(row['Middle marker'])
    for glottocode, language_markers in aggregated_markers.items():
        yield {
            'ID': f'{glottocode}-middle-markers',
            'Language_ID': glottocode,
            'Parameter_ID': 'middle-markers',
            'Value': ' / '.join(language_markers),
        }



def cldf_schema(cldf):
    cldf.add_component('LanguageTable')
    cldf.add_component('ParameterTable')
    cldf.add_component('CodeTable', 'Map_Icon')
    cldf.add_table(
        'constructions.csv',
        'http://cldf.clld.org/v1.0/terms.rdf#id',
        'http://cldf.clld.org/v1.0/terms.rdf#languageReference',
        'http://cldf.clld.org/v1.0/terms.rdf#name',
        'http://cldf.clld.org/v1.0/terms.rdf#description',
        'http://cldf.clld.org/v1.0/terms.rdf#source')
    cldf.add_table(
        'cvalues.csv',
        'http://cldf.clld.org/v1.0/terms.rdf#id',
        'Construction_ID',
        'http://cldf.clld.org/v1.0/terms.rdf#parameterReference',
        'http://cldf.clld.org/v1.0/terms.rdf#codeReference',
        'http://cldf.clld.org/v1.0/terms.rdf#value')
    cldf.add_foreign_key(
        'cvalues.csv', 'Construction_ID',
        'constructions.csv', 'ID')


class Dataset(BaseDataset):
    dir = pathlib.Path(__file__).parent
    id = "inglesemiddlevoice"

    def cldf_specs(self):
        return CLDFSpec(
            module='StructureDataset',
            dir=self.cldf_dir,
            metadata_fname='cldf-metadata.json')

    def cmd_download(self, _args):
        """
        Download files to the raw/ directory. You can use helpers methods of `self.raw_dir`, e.g.

        >>> self.raw_dir.download(url, fname)
        """

    def cmd_makecldf(self, args):
        """
        Convert the raw data to a CLDF dataset.

        >>> args.writer.objects['LanguageTable'].append(...)
        """

        # read data

        raw_data = [
            {k: v.strip() for k, v in row.items() if v.strip()}
            for row in self.raw_dir.read_csv(
                'Database_middlevoice_final.csv', delimiter=';', dicts=True)]
        cparameters = read_parameters(self.etc_dir.read_csv(
            'cparameters.csv', dicts=True))
        lparameters = read_parameters(self.etc_dir.read_csv(
            'lparameters.csv', dicts=True))
        codes = read_ccodes(
            self.etc_dir.read_csv('ccodes.csv', dicts=True),
            cparameters, lparameters)
        sources = parse_file(self.raw_dir / 'sources.bib', 'bibtex')

        # process data

        # double-check the parameter table against the column name
        data_columns = {k for row in raw_data for k in row}
        for original_name in cparameters:
            assert original_name in data_columns, original_name

        languages = make_languages(raw_data, args.glottolog.api)
        markers = make_markers(raw_data, sources.entries)
        marker_values = make_marker_values(raw_data, markers, cparameters, codes)

        lvalues = make_lvalues(raw_data, lparameters, codes)
        lvalues.extend(iter_aggregated_markers(raw_data))
        # intersperse the aggregated markers with the other values
        language_order = {}
        for i, r in enumerate(lvalues, 0):
            if (gc := r['Language_ID']) not in language_order:
                language_order[gc] = i
        lvalues.sort(key=lambda r: (language_order[r['Language_ID']], r['Parameter_ID']))

        # write cldf

        cldf_schema(args.writer.cldf)

        args.writer.objects['LanguageTable'] = languages
        args.writer.objects['ParameterTable'] = [
            *cparameters.values(),
            *lparameters.values(),
            {'ID': 'middle-markers', 'Name': 'Middle markers'}]
        args.writer.objects['CodeTable'] = codes.values()
        args.writer.objects['ValueTable'] = lvalues
        args.writer.objects['constructions.csv'] = markers.values()
        args.writer.objects['cvalues.csv'] = marker_values
        args.writer.cldf.add_sources(sources)
