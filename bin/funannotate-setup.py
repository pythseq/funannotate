#!/usr/bin/env python

import sys, os, subprocess, inspect, argparse, urllib2, datetime, hashlib, socket, shutil,errno
import xml.etree.cElementTree as cElementTree
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)
import lib.library as lib

#setup menu with argparse
class MyFormatter(argparse.ArgumentDefaultsHelpFormatter):
    def __init__(self, prog):
        super(MyFormatter, self).__init__(prog, max_help_position=48)
parser = argparse.ArgumentParser(prog='funannotate-setup.py', usage="%(prog)s [options] -m all -d path/to/database",
    description = '''Download/setup databases for funannotate''',
    epilog = """Written by Jon Palmer (2017) nextgenusfs@gmail.com""",
    formatter_class = MyFormatter)
parser.add_argument('-i', '--install', nargs='+', default=['all'], choices=['all', 'merops', 'uniprot', 'dbCAN', 'pfam', 'repeats', 'go', 'mibig', 'interpro', 'busco_outgroups', 'gene2product', 'busco'], help='Databases to download/install')
parser.add_argument('-d', '--database', help='Path to database')
parser.add_argument('-u', '--update', action='store_true', help='Check if new DB is availabe and update')
parser.add_argument('-f', '--force', action='store_true', help='Overwrite current database')
parser.add_argument('-b', '--busco_db', default=['dikarya'], nargs='+', choices=['all','fungi','microsporidia','dikarya','ascomycota','pezizomycotina','eurotiomycetes','sordariomycetes','saccharomycetes','saccharomycetales','basidiomycota','eukaryota','protists','alveolata_stramenophiles','metazoa','nematoda','arthropoda','insecta','endopterygota','hymenoptera','diptera','vertebrata','actinopterygii','tetrapoda','aves','mammalia','euarchontoglires','laurasiatheria','embryophyta'], help='choose which busco databases to install')
args=parser.parse_args()

def calcmd5(file):
    md5local = None
    with open(file, 'rb') as infile:
        data = infile.read()
        md5local = hashlib.md5(data).hexdigest()
    return md5local

def calcmd5remote(url, max_file_size=100*1024*1024):
    remote = urllib2.urlopen(url)
    hash = hashlib.md5()
    total_read = 0
    while True:
        data = remote.read(4096)
        total_read += 4096
        if not data or total_read > max_file_size:
            break
        hash.update(data)
    return hash.hexdigest()

def check4newDB(name, infoDB):
    #check remote md5 with stored in database
    if '-' in name:
        checkname = name.split('-')[0]
    else:
        checkname = name
    if not checkname in infoDB:
        lib.log.error("%s not found in database" % name)
        return True
    else:
        oldmd5 = infoDB[checkname][5]
        newmd5 = calcmd5remote(lib.DBURL.get(name))
        lib.log.debug("%s database, Old md5: %s; New md5: %s" % (name, oldmd5, newmd5))
        if oldmd5 == newmd5:
            lib.log.info("%s database is current." % name)
            return False
        else:
            lib.log.info("%s database is out of date, updating." % name)
            return True
    
def download(url, name):
    file_name = name
    try:
        u = urllib2.urlopen(url)
        f = open(file_name, 'wb')
        meta = u.info()
        file_size = int(meta.getheaders("Content-Length")[0])
        lib.log.info("Downloading: {0} Bytes: {1}".format(url, file_size))
        file_size_dl = 0
        block_sz = 8192
        while True:
            buffer = u.read(block_sz)
            if not buffer:
                break
            file_size_dl += len(buffer)
            f.write(buffer)
            p = float(file_size_dl) / file_size
            status = r"{0}  [{1:.2%}]".format(file_size_dl, p)
            status = status + chr(8)*(len(status)+1)
            sys.stdout.write(status)
        sys.stdout.flush()
        f.close()
    except socket.error as e:
        if e.errno != errno.ECONNRESET:
            raise
        pass

def meropsDB(info, force=False):
    fasta = os.path.join(FUNDB, 'merops_scan.lib')
    filtered = os.path.join(FUNDB, 'merops.formatted.fa')
    database = os.path.join(FUNDB, 'merops.dmnd')
    if os.path.isfile(fasta) and args.update and not force:
        if check4newDB('merops', info):
            force=True
    if not os.path.isfile(fasta) or force:
        lib.log.info('Downloading Merops database')
        download(lib.DBURL.get('merops'), fasta)
        md5 = calcmd5(fasta)
        #reformat fasta headers
        with open(filtered, 'w') as filtout:
            with open(fasta, 'rU') as infile:
                for line in infile:
                    if line.startswith('>'):
                        line = line.rstrip()
                        ID = line.split()[0]
                        family = line.split('#')[1]
                        filtout.write('{:} {:}\n'.format(ID, family))
                    else:
                        filtout.write(line)
        lib.log.info('Building diamond database')
        cmd = ['diamond', 'makedb', '--in', 'merops.formatted.fa', '--db', 'merops']
        lib.runSubprocess(cmd, os.path.join(FUNDB), lib.log)
        num_records = lib.countfasta(filtered)
        info['merops'] = ('diamond', database, '12.0', '2017-10-04', num_records, md5)
    type, name, version, date, records, checksum = info.get('merops')
    lib.log.info('MEROPS Database: version={:} date={:} records={:,}'.format(version, date, records))

def uniprotDB(info, force=False):
    '''
    download swissprot/uniprot database, format for diamond, and output date of database
    '''
    fasta = os.path.join(FUNDB, 'uniprot_sprot.fasta')
    database = os.path.join(FUNDB, 'uniprot.dmnd')
    versionfile = os.path.join(FUNDB, 'uniprot.release-date.txt')
    if os.path.isfile(fasta) and args.update and not force:
        if check4newDB('uniprot-release', info):
            force=True
    if not os.path.isfile(fasta) or force:
        lib.log.info('Downloading UniProtKB/SwissProt database')
        download(lib.DBURL.get('uniprot'), fasta+'.gz')
        subprocess.call(['gunzip', '-f', 'uniprot_sprot.fasta.gz'], cwd=os.path.join(FUNDB))
        download(lib.DBURL.get('uniprot-release'), versionfile)
        md5 = calcmd5(versionfile)
        unidate = ''
        univers = ''
        with open(versionfile, 'rU') as infile:
            for line in infile:
                if line.startswith('UniProtKB/Swiss-Prot Release'):
                    rest, datepart = line.split(' of ')
                    unidate = datetime.datetime.strptime(datepart.rstrip(), "%d-%b-%Y").strftime("%Y-%m-%d") 
                    univers = rest.split(' ')[-1]
        lib.log.info('Building diamond database')
        cmd = ['diamond', 'makedb', '--in', 'uniprot_sprot.fasta', '--db', 'uniprot']
        lib.runSubprocess(cmd, os.path.join(FUNDB), lib.log)
        num_records = lib.countfasta(os.path.join(FUNDB, 'uniprot_sprot.fasta'))
        info['uniprot'] = ('diamond', database, univers, unidate, num_records, md5)
    type, name, version, date, records, checksum = info.get('uniprot')
    lib.log.info('UniProtKB Database: version={:} date={:} records={:,}'.format(version, date, records))
                
def dbCANDB(info, force=False):
    hmm = os.path.join(FUNDB, 'dbCAN.hmm')
    familyinfo = os.path.join(FUNDB, 'dbCAN-fam-HMMs.txt')
    versionfile = os.path.join(FUNDB, 'dbCAN.changelog.txt')
    if os.path.isfile(hmm) and args.update and not force:
        if check4newDB('dbCAN', info):
            force=True
    if not os.path.isfile(hmm) or force:
        lib.log.info('Downloading dbCAN database')
        download(lib.DBURL.get('dbCAN'), os.path.join(FUNDB,'dbCAN.tmp'))
        md5 = calcmd5(os.path.join(FUNDB,'dbCAN.tmp'))
        download(lib.DBURL.get('dbCAN-tsv'), familyinfo)
        download(lib.DBURL.get('dbCAN-log'), versionfile)
        num_records = 0
        dbdate = ''
        dbvers = ''
        with open(hmm, 'w') as out:
            with open(os.path.join(FUNDB,'dbCAN.tmp'), 'rU') as input:
                for line in input:
                    if line.startswith('NAME'):
                        num_records += 1
                        line = line.replace('.hmm\n', '\n')
                    out.write(line)
        with open(versionfile, 'rU') as infile:
            head = [next(infile) for x in xrange(2)]
        dbdate = head[1].replace('# ', '').rstrip()
        dbvers = head[0].split(' ')[-1].rstrip()
        dbdate = datetime.datetime.strptime(dbdate, "%m/%d/%Y").strftime("%Y-%m-%d") 
        lib.log.info('Creating dbCAN HMM database')
        cmd = ['hmmpress', 'dbCAN.hmm']
        lib.runSubprocess(cmd, os.path.join(FUNDB), lib.log)
        info['dbCAN'] = ('hmmer3', hmm, dbvers, dbdate, num_records, md5)
        os.remove(os.path.join(FUNDB,'dbCAN.tmp'))
    type, name, version, date, records, checksum = info.get('dbCAN')
    lib.log.info('dbCAN Database: version={:} date={:} records={:,}'.format(version, date, records))

    
def pfamDB(info, force=False):
    hmm = os.path.join(FUNDB, 'Pfam-A.hmm')
    familyinfo = os.path.join(FUNDB, 'Pfam-A.clans.tsv')
    versionfile = os.path.join(FUNDB, 'Pfam.version')
    if os.path.isfile(hmm) and args.update and not force:
        if check4newDB('pfam-log', info):
            force=True
    if not os.path.isfile(hmm) or force:
        lib.log.info('Downloading Pfam database')
        download(lib.DBURL.get('pfam'), hmm+'.gz')
        subprocess.call(['gunzip', '-f', 'Pfam-A.hmm.gz'], cwd=os.path.join(FUNDB))
        download(lib.DBURL.get('pfam-tsv'), familyinfo+'.gz')
        subprocess.call(['gunzip', '-f', 'Pfam-A.clans.tsv.gz'], cwd=os.path.join(FUNDB))
        download(lib.DBURL.get('pfam-log'), versionfile+'.gz')
        md5 = calcmd5(versionfile+'.gz')
        subprocess.call(['gunzip', '-f', 'Pfam.version.gz'], cwd=os.path.join(FUNDB))
        num_records = 0
        pfamdate = ''
        pfamvers = ''
        with open(versionfile, 'rU') as input:
            for line in input:
                if line.startswith('Pfam release'):
                    pfamvers = line.split(': ')[-1].rstrip()
                if line.startswith('Pfam-A families'):
                    num_records = int(line.split(': ')[-1].rstrip())
                if line.startswith('Date'):
                    pfamdate = line.split(': ')[-1].rstrip()
        lib.log.info('Creating Pfam HMM database')
        cmd = ['hmmpress', 'Pfam-A.hmm']
        lib.runSubprocess(cmd, os.path.join(FUNDB), lib.log)
        info['pfam'] = ('hmmer3', hmm, pfamvers, pfamdate,  num_records, md5)
    type, name, version, date, records, checksum = info.get('pfam')
    lib.log.info('Pfam Database: version={:} date={:} records={:,}'.format(version, date, records))

def repeatDB(info, force=False):
    fasta = os.path.join(FUNDB, 'funannotate.repeat.proteins.fa')
    filtered = os.path.join(FUNDB, 'funannotate.repeats.reformat.fa')
    database = os.path.join(FUNDB, 'repeats.dmnd')
    if os.path.isfile(fasta) and args.update and not force:
        if check4newDB('repeats', info):
            force=True
    if not os.path.isfile(fasta) or force:
        lib.log.info('Downloading Repeat database')
        download(lib.DBURL.get('repeats'), fasta+'.tar.gz')
        md5 = calcmd5(fasta+'.tar.gz')
        subprocess.call(['tar', '-zxf', 'funannotate.repeat.proteins.fa.tar.gz'], cwd=os.path.join(FUNDB))
        with open(filtered, 'w') as out:
            with open(fasta, 'rU') as infile:
                for line in infile:
                    #this repeat fasta file has messed up headers....
                    if line.startswith('>'):
                        line = line.replace('#', '_')
                        line = line.replace('/', '-')
                        line = line.replace('&', '')
                    out.write(line)
        lib.log.info('Building diamond database')
        cmd = ['diamond', 'makedb', '--in', 'funannotate.repeats.reformat.fa', '--db', 'repeats', '-parse_seqids']
        lib.runSubprocess(cmd, os.path.join(FUNDB), lib.log)
        num_records = lib.countfasta(filtered)
        info['repeats'] = ('diamond', database, '1.0', today, num_records, md5)
    type, name, version, date, records, checksum = info.get('repeats')
    lib.log.info('Repeat Database: version={:} date={:} records={:,}'.format(version, date, records))
        
def outgroupsDB(info, force=False):
    OutGroups = os.path.join(FUNDB, 'outgroups')
    if os.path.isdir(OutGroups) and args.update and not force:
        if check4newDB('outgroups', info):
            force=True
    if not os.path.isdir(OutGroups) or force:
        lib.log.info('Downloading pre-computed BUSCO outgroups')
        if os.path.isdir(os.path.join(FUNDB, 'outgroups')):
        	shutil.rmtree(os.path.join(FUNDB, 'outgroups'))
        download(lib.DBURL.get('outgroups'), os.path.join(FUNDB, 'busco_outgroups.tar.gz'))
        md5 = calcmd5(os.path.join(FUNDB, 'busco_outgroups.tar.gz'))
        subprocess.call(['tar', '-zxf', 'busco_outgroups.tar.gz'], cwd=os.path.join(FUNDB))
        num_records = len([name for name in os.listdir(OutGroups) if os.path.isfile(os.path.join(OutGroups, name))])
        info['busco_outgroups'] = ('outgroups', OutGroups, '1.0', today,  num_records, md5)
    type, name, version, date, records, checksum = info.get('busco_outgroups')
    lib.log.info('BUSCO outgroups: version={:} date={:} records={:,}'.format(version, date, records))
        
def goDB(info, force=False):
    goOBO = os.path.join(FUNDB, 'go.obo')
    if os.path.isfile(goOBO) and args.update and not force:
        if check4newDB('go-obo', info):
            force=True
    if not os.path.isfile(goOBO) or force:
        lib.log.info('Downloading GO Ontology database')
        download(lib.DBURL.get('go-obo'), goOBO)
        md5 = calcmd5(goOBO)
        num_records = 0
        version = ''
        with open(goOBO, 'rU') as infile:
            for line in infile:
                if line.startswith('data-version:'):
                    version = line.split(' ')[1].rstrip().replace('releases/', '')
                if line.startswith('[Term]'):
                    num_records += 1
        info['go'] = ('text', goOBO, version, version,  num_records, md5)
    type, name, version, date, records, checksum = info.get('go')
    lib.log.info('GO ontology version={:} date={:} records={:,}'.format(version, date, records))
        
def mibigDB(info, force=False):
    fasta = os.path.join(FUNDB, 'mibig.fa')
    database = os.path.join(FUNDB, 'mibig.dmnd')
    if os.path.isfile(fasta) and args.update and not force:
        if check4newDB('mibig', info):
            force=True
    if not os.path.isfile(fasta) or force:
        lib.log.info('Downloading MiBIG Secondary Metabolism database')
        download(lib.DBURL.get('mibig'), fasta)
        md5 = calcmd5(fasta)
        version = os.path.basename(lib.DBURL.get('mibig')).split('_')[-1].replace('.fasta', '')
        lib.log.info('Building diamond database')
        cmd = ['diamond', 'makedb', '--in', 'mibig.fa', '--db', 'mibig']
        lib.runSubprocess(cmd, os.path.join(FUNDB), lib.log)
        num_records = lib.countfasta(fasta)
        info['mibig'] = ('diamond', database, version, today, num_records, md5)
    type, name, version, date, records, checksum = info.get('mibig')
    lib.log.info('MiBIG Database: version={:} date={:} records={:,}'.format(version, date, records))
        
def interproDB(info, force=False):
    iprXML = os.path.join(FUNDB, 'interpro.xml')
    if os.path.isfile(iprXML) and args.update and not force:
        if check4newDB('interpro', info):
            force=True
    if not os.path.isfile(iprXML) or force:
        lib.log.info('Downloading InterProScan Mapping file')
        download(lib.DBURL.get('interpro'), iprXML+'.gz')
        md5 = calcmd5(iprXML+'.gz')
        subprocess.call(['gunzip', '-f', 'interpro.xml.gz'], cwd=os.path.join(FUNDB))
        num_records = ''
        version = ''
        iprdate = ''
        for event, elem in cElementTree.iterparse(iprXML):
            if elem.tag == 'release':
                for x in elem.getchildren():
                    if x.attrib['dbname'] == 'INTERPRO':
                        num_records = int(x.attrib['entry_count'])
                        version = x.attrib['version']
                        iprdate = x.attrib['file_date']
        iprdate = datetime.datetime.strptime(iprdate, "%d-%b-%y").strftime("%Y-%m-%d")            
        info['interpro'] = ('xml', iprXML, version, iprdate, num_records, md5)
    type, name, version, date, records, checksum = info.get('interpro')
    lib.log.info('InterProScan XML: version={:} date={:} records={:,}'.format(version, date, records))

def curatedDB(info, force=False):
    curatedFile = os.path.join(FUNDB, 'ncbi_cleaned_gene_products.txt')
    if os.path.isfile(curatedFile) and args.update and not force:
        if check4newDB('gene2product', info):
            force=True
    if not os.path.isfile(curatedFile) or force:
        lib.log.info('Downloaded curated gene names and product descriptions')
        download(lib.DBURL.get('gene2product'), curatedFile)
        md5 = calcmd5(curatedFile)
        num_records = 0
        curdate = ''
        version = ''
        with open(curatedFile, 'rU') as infile:
            for line in infile:
                if line.startswith('#version'):
                    version = line.split(' ')[-1].rstrip()
                elif line.startswith('#Date'):
                    curdate = line.split(' ')[-1].rstrip()
                else:
                    num_records += 1
        curdate = datetime.datetime.strptime(curdate, "%m-%d-%Y").strftime("%Y-%m-%d")
        info['gene2product'] = ('text', curatedFile, version, curdate, num_records, md5)
    type, name, version, date, records, checksum = info.get('gene2product')
    lib.log.info('Gene2Product: version={:} date={:} records={:,}'.format(version, date, records))

def download_buscos(name, force=False):
    #name is a list
    if 'all' in name:
        installList = ['fungi','microsporidia','dikarya','ascomycota','pezizomycotina','eurotiomycetes','sordariomycetes','saccharomycetes','saccharomycetales','basidiomycota','eukaryota','protists','alveolata_stramenophiles','metazoa','nematoda','arthropoda','insecta','endopterygota','hymenoptera','diptera','vertebrata','actinopterygii','tetrapoda','aves','mammalia','euarchontoglires','laurasiatheria','embryophyta']
        lib.log.info("Downloading all %i busco models" % len(installList))
    else:
        installList = name
        lib.log.info("Downloading busco models: %s" % ', '.join(installList))
    for i in installList:
        if i in lib.busco_links:
            if not os.path.isdir(os.path.join(FUNDB, i)) or force:
                address = lib.busco_links.get(i)[0]
                filename = os.path.join(FUNDB, i+'.tar.gz')
                foldername = os.path.join(FUNDB, lib.busco_links.get(i)[1])
                download(address, filename)
                cmd = ['tar', '-zxf', i+'.tar.gz']
                lib.runSubprocess(cmd, os.path.join(FUNDB), lib.log)
                os.rename(foldername, os.path.join(FUNDB, i))


#create log file
log_name = 'funannotate-setup.log'
if os.path.isfile(log_name):
    os.remove(log_name)

#initialize script, log system info and cmd issue at runtime
lib.setupLogging(log_name)
cmd_args = " ".join(sys.argv)+'\n'
lib.log.debug(cmd_args)
print("-------------------------------------------------------")
lib.SystemInfo()

#get version of funannotate
version = lib.get_version()
lib.log.info("Running %s" % version)

#look for environmental variable if -d not passed
if args.database:
    FUNDB = args.database
else:
    try:
        FUNDB = os.environ["FUNANNOTATE_DB"]
    except KeyError:
        lib.log.error('$FUNANNOTATE_DB variable not found, specify DB location with -d,--database option')
        sys.exit(1)
lib.log.info("Database location: %s" % FUNDB)

#create directory if doesn't exist
if not os.path.isdir(FUNDB):
    os.makedirs(FUNDB)


global today
today = datetime.datetime.today().strftime('%Y-%m-%d')

installdbs = []
if 'all' in args.install:
    installdbs = ['merops', 'uniprot', 'dbCAN', 'pfam', 'repeats', 'go', 'mibig', 'interpro', 'busco_outgroups', 'gene2product', 'busco']
else:
    installdbs = args.install

#if text file with DB info is in database folder, parse into Dictionary
DatabaseFile = os.path.join(FUNDB, 'funannotate-db-info.txt')
DatabaseInfo = {}
if os.path.isfile(DatabaseFile):
    with open(DatabaseFile, 'rU') as inDB:
        for line in inDB:
            line = line.rstrip()
            try:
                db, type, name, version, date, records, md5checksum = line.split('\t')
                DatabaseInfo[db] = (type, name, version, date, int(records), md5checksum)
            except ValueError:
                pass

if args.update and not args.force:
    lib.log.info("Checking for newer versions of database files")
    
for x in installdbs:
    if x == 'uniprot':
        uniprotDB(DatabaseInfo, args.force)
    elif x == 'merops':
        meropsDB(DatabaseInfo, args.force)
    elif x == 'dbCAN':
        dbCANDB(DatabaseInfo, args.force)
    elif x == 'pfam':
        pfamDB(DatabaseInfo, args.force)
    elif x == 'repeats':
        repeatDB(DatabaseInfo, args.force)
    elif x == 'go':
        goDB(DatabaseInfo, args.force)
    elif x == 'interpro':
       interproDB(DatabaseInfo, args.force)
    elif x == 'mibig':
        mibigDB(DatabaseInfo, args.force)
    elif x == 'busco_outgroups':
        outgroupsDB(DatabaseInfo, args.force)
    elif x == 'gene2product':
        curatedDB(DatabaseInfo, args.force)
    elif x == 'busco':
        download_buscos(args.busco_db, args.force)
    
#output the database text file and print to terminal        
with open(DatabaseFile, 'w') as outDB:
    for k,v in DatabaseInfo.items():
        data = '%s\t%s\t%s\t%s\t%s\t%i\t%s' % (k, v[0], v[1], v[2], v[3], v[4], v[5])
        outDB.write('{:}\n'.format(data))
if args.database:
    lib.log.info('Funannoate setup complete. Add this to ~/.bash_profile or ~/.bash_aliases:\n\n\texport FUNANNOTATE_DB={:}\n'.format(os.path.abspath(args.database)))
sys.exit(1)

