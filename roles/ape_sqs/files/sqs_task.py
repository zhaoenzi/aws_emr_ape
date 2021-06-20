# -*- coding: UTF-8 -*-
import boto3
import json
from ansible.cli.playbook import PlaybookCLI
import traceback
import os
import sys
import time


def event_handler(aws_region,event,meta_base,private_key_path):
    is_ok = False

    try:
        if is_resize_complete(event):
            cluster_id = event['detail']["clusterId"]
            untaged_ins = get_untaged_instances(aws_region,cluster_id)
            if len(untaged_ins) == 0:
                print("no untaged instance")
                return True
            hosts = ",".join(untaged_ins)+","
            print("untaged host: {0}".format(hosts))
            ssh_user = ""
            private_key = ""
            for base in meta_base:
                if base["cluster_id"] == cluster_id:
                    ssh_user = base["ssh_user"]
                    private_key = base["private_key"]
            cli = PlaybookCLI([" ", '-i', hosts, '-u', ssh_user, '--private-key', private_key_path+"/"+private_key, "--extra-vars", "deploy_cluster_id="+cluster_id, "exporter_playbook.yml"])
            results = cli.run()
            if results == 0:
                is_ok = True
                print("ansible install exporter ok")
            else:
                print("ansible install exporter error")
        else:
            print("ERM State Change resize not complete.")
    except Exception as error:
        print("ape run error: ", error)
        # traceback.print_exc()
    return is_ok


def is_resize_complete(event):
    if (event['detail-type'] == "EMR Instance Group State Change"
        or event['detail-type'] == "EMR Instance Fleet State Change") \
            and "is complete" in event['detail']["message"] \
            and (event['detail']["state"] == "RUNNING" or event['detail']["state"] == "RESIZING"):
        return True
    else:
        return False


def get_untaged_instances(aws_region,cluster_id):
    emr_client = boto3.client('emr',region_name=aws_region)
    response = emr_client.describe_cluster(
        ClusterId=cluster_id
    )
    untaged_list = []
    if response["Cluster"]["InstanceCollectionType"] == "INSTANCE_GROUP":
        emr_response = emr_client.list_instances(
            ClusterId=cluster_id,
            InstanceGroupTypes=['CORE', 'TASK'],
            InstanceStates=[
                'RUNNING'
            ],
        )
        untaged_list.extend(filter_instance(aws_region,emr_response))

    if response["Cluster"]["InstanceCollectionType"] == "INSTANCE_FLEET":
        emr_response_task = emr_client.list_instances(
            ClusterId=cluster_id,
            InstanceFleetType='TASK',
            InstanceStates=[
                'RUNNING'
            ],
        )
        untaged_list.extend(filter_instance(aws_region,emr_response_task))
        emr_response_core = emr_client.list_instances(
            ClusterId=cluster_id,
            InstanceFleetType='CORE',
            InstanceStates=[
                'RUNNING'
            ],
        )
        untaged_list.extend(filter_instance(aws_region,emr_response_core))
    return list(set(untaged_list))


def filter_instance(aws_region,emr_instances):
    ec2_client = boto3.client('ec2',region_name=aws_region)
    ins_list = []
    ins_dict = {}
    for ins in emr_instances["Instances"]:
        pubIP = ins["PublicIpAddress"]
        ec2ID = ins["Ec2InstanceId"]
        # ins["PrivateIpAddress"]
        ins_list.append(ec2ID)
        ins_dict[ec2ID] = pubIP
    ec2_response = ec2_client.describe_tags(
        Filters=[
            {
                'Name': 'resource-id',
                'Values': ins_list
            }
        ],
    )
    untag_list = []
    for tag in ec2_response["Tags"]:
        if tag["Key"] == "node_exporter" or tag["Key"] == "jmx_exporter_nn" \
                or tag["Key"] == "jmx_exporter_dn" \
                or tag["Key"] == "jmx_exporter_rm" \
                or tag["Key"] == "jmx_exporter_nm":
            ec2_id = tag["ResourceId"]
            ins_dict[ec2_id]=""

    for key, value in ins_dict.items():
        if value != "":
            untag_list.append(value)
    return list(set(untag_list))


def process_msg(meta,private_key_path):
    meta_base = meta["base"]
    aws_region = meta["aws_region"]
    sqs_queue_name = meta["sqs_queue_name"]
    sqs = boto3.resource('sqs',region_name=aws_region)
    while 1:
        try:
            queue = sqs.get_queue_by_name(QueueName=sqs_queue_name)
            if queue != None:
                break
        except Exception as error:
            print("queue is not  ok, after 15s retry ... ", error)
            time.sleep(15)
    while 1:
        # print("wait message")
        for message in queue.receive_messages(AttributeNames=["All"],MaxNumberOfMessages=3, WaitTimeSeconds=5):
            # Get the custom author message attribute if it was set
            try:
                print(message.body)
                event = json.loads(message.body)
                # print(event)
                res = event_handler(aws_region,event,meta_base,private_key_path)
                if res:
                    print("delete msg")
                    message.delete()
            except Exception as error:
                print("process sqs  error: ", error)


def load_json_from_file(file_path):
    with open(file_path, 'r') as f:
        data = json.load(f)
        return data


if __name__ == '__main__':
    meta_json_file = sys.argv[1]
    private_key_path = sys.argv[2]
    meta = load_json_from_file(meta_json_file)
    process_msg(meta,private_key_path)
