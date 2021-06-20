#!/bin/sh
run_cluster_name=$1
# shellcheck disable=SC2164
base_path=$(cd "$(dirname "$0")"; pwd)
private_key_path=$base_path"/keys/"
meta_file=$base_path"/meta.json"

cat $meta_file |jq -c '.base[]'| while read i;
do
cluster_name=`echo $i | jq -c -r '.cluster_name'`
#echo $i | jq -c  -r '.cluster_name'
#echo $cluster_name
if [ $cluster_name = $run_cluster_name ];then
  private_key=`echo $i | jq -c -r  '.private_key'`
  key=$private_key_path$private_key
  echo $key
fi
done