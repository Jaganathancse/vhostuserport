import argparse
import json
import os
import paramiko
import re
import subprocess
import sys
import xmltodict

# Gets the profile name for flavor name
def get_profile_name(flavor_name):
    cmd = "openstack flavor show " + flavor_name
    output = subprocess.check_output(cmd,shell=True)
    properties = ''
    for line in output.split('\n'):
        if 'properties' in line:
            properties = line
    profile = ''
    if properties:
        profile_index = properties.index('capabilities:profile=')
        if profile_index >=0:
            profile_start_index = profile_index + len('capabilities:profile=') + 1
            profile_end_index = properties.index('\'', profile_start_index, len(properties))
            profile = properties[profile_start_index:profile_end_index]
    return profile

# Gets the first matching node UUID for flavor name
def get_node_uuid(flavor_name):
    node_uuid = ''
    profile_name = get_profile_name(flavor_name)
    cmd = "openstack overcloud profiles list -f json"
    output = subprocess.check_output(cmd,shell=True)
    profiles_list = json.loads(output)
    for profile in profiles_list:
        if profile["Current Profile"] == profile_name:
            node_uuid = profile["Node UUID"]
            break
    return node_uuid.strip()


# Gets the flavor name for role name
def get_flavor_name(role_name):
    flavor_name = ''
    param_key = 'Overcloud' + role_name + 'Flavor'
    cmd = "mistral run-action tripleo.parameters.get"
    output = subprocess.check_output(cmd,shell=True)
    result = json.loads(output)
    if result and result.get('result', {}):
        env = result.get('result', {}).get('mistral_environment_parameters', {})
        if not env:
            env = result.get('result', {}).get('environment_parameters', {})
        if env:
            flavor_name = env.get(param_key, '')
    return flavor_name

# gets the instance UUID by node UUID
def get_instance_uuid(node_uuid):
    instance_uuid = ''
    cmd = "ironic --json node-list"
    output = subprocess.check_output(cmd, shell=True)
    node_list = json.loads(output)
    for node in node_list:
        if node["uuid"] == node_uuid:
            instance_uuid = node["instance_uuid"] 
            break
    return instance_uuid.strip()


# gets the host ip address from instance UUID
def get_host_ip(instance_uuid):
    cmd = 'nova show ' + instance_uuid + ' | grep "ctlplane network"'
    output = subprocess.check_output(cmd, shell=True)
    host_ip = output.replace('ctlplane network', '').strip(' |\n')
    return host_ip


# get vm dumpxml
def get_vm_list_from_env(client):
    vm_list = []
    cmd = 'sudo virsh list --all'
    stdin, stdout, stderr = client.exec_command(cmd)
    cmd_line = str(stdout.read())
    if cmd_line:
        for line in cmd_line.split("\n"):
            if "instance" in line:
                vm_list.append(line.strip().split(' ')[0].strip())
    return vm_list

def get_vm_dumpxml_from_env(client, vm_id):
    vm_xml = {}
    cmd = 'sudo virsh dumpxml '+vm_id
    stdin, stdout, stderr = client.exec_command(cmd)
    cmd_line = str(stdout.read())
    if cmd_line:
        vm_xml = xmltodict.parse(cmd_line)
    return vm_xml

def getvhostuserports():
   ports = {}
   try:
        opts = parse_opts(sys.argv)
        flavor = get_flavor_name(opts.role_name)
        node_uuid = get_node_uuid(flavor)
        instance_uuid = get_instance_uuid(node_uuid)
        host_ip = get_host_ip(instance_uuid)
        # SSH access
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.load_system_host_keys()
        client.connect(host_ip, username='heat-admin')
        client.invoke_shell()
        vm_list = get_vm_list_from_env(client)
        print(vm_list)
        for vm_id in vm_list:
             vm_xml = get_vm_dumpxml_from_env(client, vm_id)
             print(vm_xml['domain']['devices']['interface'])
             interfaces = vm_xml['domain']['devices']['interface']
             for interface in interfaces:                                                    
                 if interface['@type'] == 'vhostuser' and interface['address']['@slot'] == opts.slot:
                     ports[str(vm_id)]=interface['source']['@path'].strip('/var/lib/vhost_sockets/') 
        client.close()
   except Exception as exc:
       print("Error: %s" % exc)
   print(ports)

# Gets the user input as dictionary.
def parse_opts(argv):
    parser = argparse.ArgumentParser(
        description='Interactive tool')
    parser.add_argument('-r', '--role_name',
                        metavar='ROLE NAME',
                        help="""role name.""",
                        default='')
    parser.add_argument('-s', '--slot',
                        metavar='SLOT',
                        help="""slot.""",
                        default='0x03')
    opts = parser.parse_args(argv[1:])
    return opts


if __name__ == '__main__':
    getvhostuserports()
