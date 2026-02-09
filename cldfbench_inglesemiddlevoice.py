import pathlib
import unicodedata
from collections import defaultdict

from cldfbench import CLDFSpec, Dataset as BaseDataset


ID_CHARS = (
    'abcdefghijklmnopqrstuvwxyz'
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    '0123456789-_')


def slug(s):
    return ''.join(
        c
        for c in unicodedata.normalize('NFKD', s).lower()
        if c in ID_CHARS)


def read_cparameters(csv_rows):
    return {
        row['Original_Name']: {
            'ID': slug(row['Name']),
            'Name': row['Name'],
            'Description': row['Description'],
        }
        for row in csv_rows}


def read_ccodes(csv_rows, parameters):
    return {
        (row['Original_Parameter_Name'], row['Original_Name']):
        {
            'ID': row['ID'],
            'Parameter_ID': parameters[row['Original_Parameter_Name']]['ID'],
            'Name': row['Name'],
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


def make_markers(data):
    # TODO: source column
    markers = {
        ((gc := fix_glottocode(row['Glottocode'])), row['Middle marker']): {
            'ID': '{}-{}'.format(gc, slug(row['Middle marker'])),
            'Language_ID': gc,
            'Name': row['Middle marker'],
        }
        for row in data}
    assert len(markers) == len(data), 'markers are unique'
    return markers


def make_marker_values(data, markers, cparameters, ccodes):
    return [
        {
            'Parameter_ID': (param_id := param['ID']),
            'Construction_ID': (construction_id := markers[
                fix_glottocode(row['Glottocode']), row['Middle marker']]['ID']),
            'Code_ID': (code := ccodes[param_col, value])['ID'],
            'Value': code['Name'],
            'ID': f'{construction_id}-{param_id}',
        }
        for row in data
        for param_col, param in cparameters.items()
        if (value := row.get(param_col)) and value != '_']


def make_lvalues(data):
    aggregated_markers = defaultdict(list)
    for row in data:
        aggregated_markers[fix_glottocode(row['Glottocode'])].append(row['Middle marker'])
    return [
        {
            'ID': f'{glottocode}-middle-markers',
            'Language_ID': glottocode,
            'Parameter_ID': 'middle-markers',
            'Value': ' / '.join(language_markers),
        }
        for glottocode, language_markers in aggregated_markers.items()]



def cldf_schema(cldf):
    cldf.add_component('LanguageTable')
    cldf.add_component('ParameterTable')
    cldf.add_component('CodeTable')
    cldf.add_table(
        'constructions.csv',
        'http://cldf.clld.org/v1.0/terms.rdf#id',
        'http://cldf.clld.org/v1.0/terms.rdf#languageReference',
        'http://cldf.clld.org/v1.0/terms.rdf#name',
        'http://cldf.clld.org/v1.0/terms.rdf#description')
    cldf.add_table(
        'cvalues.csv',
        'http://cldf.clld.org/v1.0/terms.rdf#id',
        'Construction_ID',
        'http://cldf.clld.org/v1.0/terms.rdf#parameterReference',
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
        cparameters = read_cparameters(self.etc_dir.read_csv(
            'cparameters.csv', dicts=True))
        ccodes = read_ccodes(
            self.etc_dir.read_csv('ccodes.csv', dicts=True),
            cparameters)
        lparameters = list(self.etc_dir.read_csv('lparameters.csv', dicts=True))

        # process data

        # double-check the parameter table against the column name
        data_columns = {k for row in raw_data for k in row}
        for original_name in cparameters:
            assert original_name in data_columns, original_name

        languages = make_languages(raw_data, args.glottolog.api)
        markers = make_markers(raw_data)
        marker_values = make_marker_values(raw_data, markers, cparameters, ccodes)

        lvalues = make_lvalues(raw_data)

        # write cldf

        cldf_schema(args.writer.cldf)

        args.writer.objects['LanguageTable'] = languages
        args.writer.objects['ParameterTable'] = [*cparameters.values(), *lparameters]
        args.writer.objects['CodeTable'] = ccodes.values()
        args.writer.objects['ValueTable'] = lvalues
        args.writer.objects['constructions.csv'] = markers.values()
        args.writer.objects['cvalues.csv'] = marker_values
