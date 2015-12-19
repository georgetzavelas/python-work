#!/bin/python

""" 
This script will takes a supplied start date and end date along with
a JSON file the defines the repos and determine the commits made to those
repos and cross-reference them with the issues in JIRA and provide details
for those specific issues.

Used the following as an example:
https://codereview.stackexchange.com/questions/41492/script-to-checkout-multiple-repositories-to-a-certain-commit-hash

Need to install the jira package: pip install jira

"""

import os
import subprocess
import json
import argparse
import shlex
from jira import JIRA
from dateutil.parser import parse

# JIRA settings
options = {
    'server': 'https://telepin.atlassian.net'
}

parser = argparse.ArgumentParser(description='Description')
parser.add_argument('--since', help='Show commits starting from this specific date. \
                    format YYYY-MM-DD', 
                    required=True)
parser.add_argument('--until', help='Show commits till this specific date. \
                    format YYYY-MM-DD',
                    required=True)

REPO_URL = 'ssh://gtzavelas@gerrit.telepin.ottawa:29418/' # ssh://jenkins@gerrit.telepin.ottawa:29418/
REPO_DIRECTORY = './'
REPO_INFO_FILE = 'rnotes.json'
repo_info_test = '{"filename": "release_notes", \
                    "repos": \
                    [{"repo": "tcs4.tcs", "info": "tcs"}, \
                     {"repo": "tcs4.paymentproviders", "info": "payment providers"},\
                     {"repo": "telepin.common", "info": "telepin common"},\
                     {"repo": "ruleengine", "info": "rule engine"},\
                     {"repo": "telepin.ibl", "info": "IBL"},\
                     {"repo": "ussdmenubuilder", "info": "ussd menu builder"},\
                     {"repo": "TelepinWebClient", "info": "web client"},\
                     {"repo": "TelepinWebServer", "info": "web server"},\
                     {"repo": "PHP", "info": "web self care"},\
                     {"repo": "appserver.jetty", "info": "app server"},\
                     {"repo": "Telepin3DAPI", "info": "3d api"},\
                     {"repo": "db.src", "info": "database sql"}\
                    ]}'
repo_info = json.loads(repo_info_test)
# repo_info = json.loads(open(REPO_INFO_FILE, 'r').read())

args = vars(parser.parse_args())
since = args['since']
until = args['until']

def get_git_commit_message_history(repo_name, since_date, until_date):
    git_log_cmd = shlex.split('git --git-dir=' + REPO_DIRECTORY + repo_name +
                              '/.git log --no-merges --all --pretty=format:"%s" \
                              --since=' + since_date + ' --until=' + until_date)
    try:
        output, error = subprocess.Popen(git_log_cmd, stdout=subprocess.PIPE).communicate()
        output_str = output.decode('ascii')
        return output_str.strip().splitlines()
    except Exception as e:
        print("ERROR: Couldn't get git history for repo %s: %s" % (repo_name, str(e)))

def get_git_commit_history(repo_name, since_date, until_date):
    git_log_cmd = shlex.split('git --git-dir=' + REPO_DIRECTORY + repo_name +
                              '/.git log --no-merges --all --pretty=format:"%h|%an|%ad|%s" \
                              --since=' + since_date + ' --until=' + until_date)
    try:
        output, error = subprocess.Popen(git_log_cmd, stdout=subprocess.PIPE).communicate()
        output_str = output.decode('ascii')
        return output_str.strip().splitlines()
    except Exception as e:
        print("ERROR: Couldn't get git history for repo %s: %s" % (repo_name, str(e)))

def get_repo_history(repo_name, since_date, until_date):

    def repo_exists(repo):
        return os.path.isdir(REPO_DIRECTORY + repo)

    def clone_repo(repo):
        clone_cmd = shlex.split("git clone %s%s %s%s" % (REPO_URL, repo, REPO_DIRECTORY, repo))
        print('cloning repo:' + repo)
        subprocess.check_call(clone_cmd)

    def pull_repo(repo):
        pull_cmd = shlex.split("git -C %s pull" % (REPO_DIRECTORY + repo))
        print('pulling from repo:' + repo)
        subprocess.check_call(pull_cmd)
    try:
        if repo_exists(repo_name):
            pull_repo(repo_name)
        else:
            clone_repo(repo_name)
    except Exception as e:
        print('ERROR: pull/clone repo failed for repo %s: %s', repo_name, str(e))
        return

#    commit_history = get_git_commit_message_history(repo_name, since_date, until_date)
#    commit_jiras = []
#    for commit in commit_history:
#        commit_jira = commit.split(' ')[0]
#        commit_jira = commit_jira.split(':')[0]
#        commit_jiras.append(commit_jira)
#    return commit_jiras
    commit_history = get_git_commit_history(repo_name, since_date, until_date)
    return commit_history;

def get_jira_details(repo_history_list):
    output_file = open(repo_info['filename'] + '_' + since + '_' + until + '.csv', 'w')
    headings = ['Issue', 'Project', 'Summary', 'Status', 'Type', 'Components', 'Reporter',
                'Created', 'Updated', 'Resolved', 'Epic', 'Fix Versions', 'PM Notes Internal', 'PM Notes External']
    output_file.write(','.join(headings))
    output_file.write('\n')
    print('Getting JIRA details for issues...')
    jira = JIRA(options, basic_auth=('noninteractive', 'etopup123'))
    for jira_from_repo in repo_history_list:
        if jira_from_repo == 'REVERT':
            continue
        try:
            issue = jira.issue(jira_from_repo, fields='summary,status,issuetype,components,created,updated,'
                                                      'resolutiondate,reporter,fixVersions,customfield_10008,'
                                                      'customfield_10600,customfield_11200,project')
        except Exception as e:
            print('Problem obtaining info about issue=' + jira_from_repo, str(e))
            output_file.write(jira_from_repo + ',Unknown,Unknown JIRA!,,,,,,,,,,,')
            output_file.write('\n')
            continue
        summary = issue.fields.summary.replace(',', ' ')
        status = issue.fields.status.name
        issuetype = issue.fields.issuetype.name
        components = []
        for component in issue.fields.components:
            components.append(component.name)
        all_components = ';'.join(components)
        created = parse(issue.fields.created).date().strftime("%Y-%m-%d")
        updated = parse(issue.fields.updated).date().strftime("%Y-%m-%d")
        resolved = ''
        if issue.fields.resolutiondate:
            resolved = parse(issue.fields.resolutiondate).date().strftime("%Y-%m-%d")
        reporter = issue.fields.reporter.displayName
        versions = []
        for version in issue.fields.fixVersions:
            versions.append(version.name)
        all_versions = ';'.join(versions)
        epic = ''
        if issue.fields.customfield_10008:
            epic = issue.fields.customfield_10008
        pm_internal = ''
        if issue.fields.customfield_10600:
            pm_internal = issue.fields.customfield_10600.replace(',', ' ')
            pm_internal = pm_internal.replace('\r\n', '|')
        pm_external = ''
        if issue.fields.customfield_11200:
            pm_external = issue.fields.customfield_11200.replace(',', ' ')
            pm_external = pm_external.replace('\r\n', '|')
        project_name = issue.fields.project.name
        try:
            issue_items = [jira_from_repo, project_name, summary, status, issuetype, all_components, reporter,
                           created, updated, resolved, epic, all_versions, pm_internal, pm_external]
            output_file.write(','.join(issue_items))
            output_file.write('\n')
        except Exception as e:
            print('JIRA field problem for issue=' + jira_from_repo, str(e))

def get_jira_from_git_details(repo_history_raw):
    commit_jiras = []
    for commit in repo_history_raw:
        commit_parts = commit.split('|')
        commit_comment = commit_parts[3]
        commit_jira = commit_comment.split(' ')[0]
        commit_jira = commit_jira.split(':')[0].upper()
        commit_jiras.append(commit_jira)
    return commit_jiras

def output_git_details(repo_history_list):
    output_file = open(repo_info['filename'] + '_git_details_' + since + '_' + until + '.csv', 'w')
    headings = ['Issue', 'Repository', 'SHA', 'Committer', 'Commit Date', 'Comment']
    print('Generating git details file...')
    output_file.write(','.join(headings))
    output_file.write('\n')

    for commit in repo_history_list:
        commit_parts = commit.split('|')
        commit_sha = commit_parts[0]
        commit_commiter = commit_parts[1]
        commit_date = parse(commit_parts[2]).strftime("%Y-%m-%d %H:%M")
        commit_comment = commit_parts[3].replace(',', ' ')
        commit_repo = commit_parts[4]
        commit_jira = commit_comment.split(' ')[0]
        commit_jira = commit_jira.split(':')[0].upper()
        output_file.write(commit_jira + ',' + commit_repo + ',' + commit_sha + ',' + commit_commiter + ',' +
                          commit_date + ',' + commit_comment)
        output_file.write('\n')

def main():
    print('Release Notes, using since=' + since + ', until=' + until)
    repo_history_list_raw = []
    repo_jira_history_list_raw = []
    for repo_json in repo_info['repos']:
        print('Inspecting repo:' + repo_json['repo'])
        repo_history_raw = get_repo_history(repo_json['repo'], since, until)
        repo_jira_history_raw = get_jira_from_git_details(repo_history_raw)
        repo_history_modified = [s + '|' + repo_json['repo'] for s in repo_history_raw]
        repo_jira_history_list_raw += repo_jira_history_raw
        repo_history_list_raw += repo_history_modified
        print('JIRA list from repo:' + ','.join(repo_jira_history_raw))
    output_git_details(repo_history_list_raw)
    repo_history_list = list(set(repo_jira_history_list_raw))
    print('JIRA consolidated list:' + ','.join(repo_history_list))
    get_jira_details(repo_history_list)


if __name__ == '__main__':
    main()
