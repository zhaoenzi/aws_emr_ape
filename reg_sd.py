# -*- coding: UTF-8 -*-
import boto3
import json
import time
import sys
import requests


def gen_exporter_instance_sd(aws_region,exporter_tag, tag_value, ip_type, cluster_id):
    ec2_client = boto3.client('ec2', region_name=aws_region)
    ip_list = []
    ec2_response = ec2_client.describe_instances(
        Filters=[
            {
                'Name': 'tag:' + exporter_tag,
                'Values': [tag_value]
            },
            {
                'Name': 'tag:aws:elasticmapreduce:job-flow-id',
                'Values': [cluster_id]
            },
        ],
    )
    for reserv in ec2_response["Reservations"]:
        instances_list = reserv["Instances"]
        for ins in instances_list:
            ip_list.append(ins[ip_type])
    return ip_list


def format_sd(metrics, job,cluster_id,cluster_name):
    file_sd = {}
    file_sd["targets"] = metrics
    labels = {}
    labels["job"] = job
    labels["cluster_id"] = cluster_id
    labels["cluster_name"] = cluster_name
    file_sd["labels"] = labels
    return file_sd


def format_consul(ip, port, name, tags):
    register_data = {}
    register_data["ID"] = name+"_"+ip
    register_data["Name"] = name
    register_data["Tags"] = tags
    register_data["Address"] = ip
    register_data["Port"] = port
    register_data["check"] = {"http": "http://" + ip + ":" + str(port) + "/metrics", "interval": "15s"}
    return register_data


def request_consul(url, payload):
    try:
        headers = {"Content-Type": "application/json"}
        res = requests.put(url, data=json.dumps(payload),headers=headers)
        if res.status_code == 200:
            print("reg ok")
            # print("reg url:{0}".format(url))
            # print("reg service: {0}".format(json.dumps(payload)))
        else:
            sys.exit(-1)
        res.raise_for_status()
    except Exception as e:
        print(e)
        sys.exit(-1)


def reg_nj_consul(service_meta, aws_region,ip_type, cluster_id,cluster_name, consul_address):
    for sm in service_meta:
        name = sm["name"]
        port = sm["port"]
        install_tag = "installed"
        service_ip_list = gen_exporter_instance_sd(aws_region,name, install_tag, ip_type, cluster_id)
        if len(service_ip_list) > 0:
            tags = [cluster_id, cluster_name, name]
            for x in service_ip_list:
                payload = format_consul(x, port, name, tags)
                request_consul(consul_address, payload)


def gen_nj_file_sd(service_meta, aws_region, ip_type, cluster_id,cluster_name):
    sd_list = []
    for sm in service_meta:
        name = sm["name"]
        port = sm["port"]
        install_tag = "installed"
        service_ip_list = gen_exporter_instance_sd(aws_region,name, install_tag, ip_type, cluster_id)
        if len(service_ip_list) > 0:
            service_sd_metric = [x + ":" + port for x in service_ip_list]
            service_file_sd = format_sd(service_sd_metric, name,cluster_id,cluster_name)
            sd_list.append(service_file_sd)
    return sd_list


def write_sd_file(prometheus_sd_dir, cluster_id, sd_str):
    write_time = time.strftime("%Y%m%d%H%M%S", time.localtime())
    file_name = prometheus_sd_dir + "/" + cluster_id + "-" + write_time + ".json"
    with open(file_name, "w") as f:
        f.write(sd_str)
        print("write file sd ok")


def load_json_from_file(file_path):
    with open(file_path, 'r') as f:
        data = json.load(f)
        return data


def process(base,aws_region):
    cluster_id = base["cluster_id"]
    cluster_name = base["cluster_name"]
    ip_type = base["ip_type"]
    prometheus_sd_dir = base["prometheus_sd_dir"]
    consul_address = base["consul_address"]
    # sleep 3s ,get jmx tag as much as possible
    time.sleep(3)
    service_meta = [
        {"name": "node_exporter", "port": 9100},
        {"name": "jmx_exporter_nn", "port": 7005},
        {"name": "jmx_exporter_dn", "port": 7006},
        {"name": "jmx_exporter_rm", "port": 7007},
        {"name": "jmx_exporter_nm", "port": 7008}
    ]
    if prometheus_sd_dir != "":
        sd_list = gen_nj_file_sd(service_meta,aws_region, ip_type, cluster_id,cluster_name)
        if len(sd_list) > 0:
            sd_str = json.dumps(sd_list)
            write_sd_file(prometheus_sd_dir, cluster_id, sd_str)
    if consul_address != "":
        reg_nj_consul(service_meta,aws_region, ip_type, cluster_id, cluster_name,consul_address)


if __name__ == '__main__':
    meta_json_file = sys.argv[1]
    deploy_cluster_id = sys.argv[2]
    meta = load_json_from_file(meta_json_file)
    meta_base = meta["base"]
    aws_region=meta["aws_region"]
    for base in meta_base:
        if base["cluster_id"] == deploy_cluster_id:
            process(base,aws_region)
