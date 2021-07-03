import csv

fp_w=open("generated_measurement.csv","w",newline="")
writer=csv.writer(fp_w)
line=["measurement_id","measurement_type","o_zone_id","d_zone_id","from_node_id","to_node_id","count","upper_bound_flag"]
writer.writerow(line)
measurement_id=1
with open("link_performance_benchmark.csv","r") as fp:
    reader=csv.DictReader(fp)
    for line in reader:
        newline=[measurement_id,"link","","",line["from_node_id"],line["to_node_id"],line["volume"],0]
        writer.writerow(newline)
        measurement_id+=1

o_vol_dict=dict()
d_vol_dict=dict()
with open("demand.csv","r") as fp:
    reader=csv.DictReader(fp)
    for line in reader:
        if float(line["volume"])>0:
            if line["o_zone_id"] in o_vol_dict:
                o_vol_dict[line["o_zone_id"]]+=float(line["volume"])
            else:
                o_vol_dict[line["o_zone_id"]]=float(line["volume"])

            if line["d_zone_id"] in d_vol_dict:
                d_vol_dict[line["d_zone_id"] ]+=float(line["volume"])
            else:
                d_vol_dict[line["d_zone_id"] ]=float(line["volume"])
           
for key,val in o_vol_dict.items():
    line=[measurement_id,"production",key,"","","",val,0]
    writer.writerow(line)
    measurement_id+=1

for key,val in d_vol_dict.items():
    line=[measurement_id,"attraction","",key,"","",val,0]
    writer.writerow(line)
    measurement_id+=1

fp_w.close()
