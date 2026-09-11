"""Bounded SNMP v1/v2c Trap receiver for NI-3.

The receiver intentionally does not persist raw packets or community strings.
SNMPv3 traps are rejected until an authenticated USM receiver exists. INFORM is
also rejected because this minimal receiver does not send protocol acknowledgements.
"""
import queue
import socket
import threading
import time

TRAP_V1 = 0xA4
INFORM = 0xA6
TRAP_V2 = 0xA7
SEQUENCE = 0x30
INTEGER = 0x02
OCTET = 0x04
OID = 0x06
IPADDRESS = 0x40
TIMETICKS = 0x43

TRAP_OID_VAR = ".1.3.6.1.6.3.1.1.4.1.0"
IFINDEX = ".1.3.6.1.2.1.2.2.1.1"
IFADMIN = ".1.3.6.1.2.1.2.2.1.7"
IFOPER = ".1.3.6.1.2.1.2.2.1.8"
STD_TRAPS = {
    ".1.3.6.1.6.3.1.1.5.1": ("COLD_START", "WARNING"),
    ".1.3.6.1.6.3.1.1.5.2": ("WARM_START", "WARNING"),
    ".1.3.6.1.6.3.1.1.5.3": ("LINK_DOWN", "MAJOR"),
    ".1.3.6.1.6.3.1.1.5.4": ("LINK_UP", "INFO"),
    ".1.3.6.1.6.3.1.1.5.5": ("AUTH_FAILURE", "WARNING"),
    ".1.3.6.1.6.3.1.1.5.6": ("EGP_NEIGHBOR_LOSS", "WARNING"),
}
V1_GENERIC = {0: ".1.3.6.1.6.3.1.1.5.1", 1: ".1.3.6.1.6.3.1.1.5.2",
              2: ".1.3.6.1.6.3.1.1.5.3", 3: ".1.3.6.1.6.3.1.1.5.4",
              4: ".1.3.6.1.6.3.1.1.5.5", 5: ".1.3.6.1.6.3.1.1.5.6"}

class TrapError(ValueError): pass

def _len(data, i):
    if i >= len(data): raise TrapError("truncated BER length")
    first=data[i]; i+=1
    if first < 0x80: return first,i
    n=first & 0x7f
    if n < 1 or n > 4 or i+n > len(data): raise TrapError("invalid BER length")
    return int.from_bytes(data[i:i+n],"big"), i+n

def _tlv(data, i=0):
    if i >= len(data): raise TrapError("truncated BER")
    tag=data[i]; n,j=_len(data,i+1); end=j+n
    if end > len(data): raise TrapError("truncated BER value")
    return tag,data[j:end],end

def _int(body): return int.from_bytes(body or b"\0","big",signed=bool(body and body[0]&0x80))
def _oid(body):
    if not body: return ""
    first=body[0]; parts=[min(first//40,2), first-(min(first//40,2)*40)]; val=0
    for b in body[1:]:
        val=(val<<7)|(b&0x7f)
        if not b&0x80: parts.append(val); val=0
    if val: raise TrapError("unterminated OID")
    return "."+".".join(map(str,parts))

def _children(body):
    out=[]; i=0
    while i < len(body):
        tag,val,i2=_tlv(body,i); out.append((tag,val)); i=i2
    return out

def _value(tag, body):
    if tag in (INTEGER, TIMETICKS): return _int(body)
    if tag == OID: return _oid(body)
    if tag == IPADDRESS: return ".".join(str(x) for x in body)
    if tag == OCTET:
        return body.decode("utf-8","replace")[:256]
    return None

def _varbinds(seq_body):
    out={}
    for tag,entry in _children(seq_body):
        if tag != SEQUENCE: continue
        fields=_children(entry)
        if len(fields) < 2 or fields[0][0] != OID: continue
        out[_oid(fields[0][1])] = _value(fields[1][0], fields[1][1])
    return out

def parse_packet(data):
    if not isinstance(data,(bytes,bytearray)) or not data or len(data) > 65535:
        raise TrapError("invalid trap packet size")
    tag,outer,end=_tlv(bytes(data),0)
    if tag != SEQUENCE or end != len(data): raise TrapError("invalid SNMP message")
    fields=_children(outer)
    if len(fields) < 3 or fields[0][0] != INTEGER or fields[1][0] != OCTET:
        raise TrapError("invalid SNMP message")
    version=_int(fields[0][1])
    if version == 3: raise TrapError("SNMPv3 trap authentication is not implemented")
    if version not in (0,1): raise TrapError("unsupported SNMP version")
    ptag,pbody=fields[2]
    if ptag == INFORM: raise TrapError("SNMP INFORM is not supported")
    result={"version":"v1" if version==0 else "v2c", "trap_oid":"", "varbinds":{}, "uptime_ticks":None}
    if version == 1:
        if ptag != TRAP_V2: raise TrapError("expected SNMPv2 trap PDU")
        p=_children(pbody)
        if len(p)<4 or p[3][0] != SEQUENCE: raise TrapError("invalid SNMPv2 trap PDU")
        vb=_varbinds(p[3][1]); result["varbinds"]=vb
        result["trap_oid"]=str(vb.get(TRAP_OID_VAR) or "")
        result["uptime_ticks"]=vb.get(".1.3.6.1.2.1.1.3.0")
    else:
        if ptag != TRAP_V1: raise TrapError("expected SNMPv1 trap PDU")
        p=_children(pbody)
        if len(p)<6 or p[0][0]!=OID or p[2][0]!=INTEGER or p[3][0]!=INTEGER or p[4][0]!=TIMETICKS or p[5][0]!=SEQUENCE:
            raise TrapError("invalid SNMPv1 trap PDU")
        enterprise=_oid(p[0][1]); generic=_int(p[2][1]); specific=_int(p[3][1])
        result.update({"generic_trap":generic,"specific_trap":specific,"uptime_ticks":_int(p[4][1])})
        result["trap_oid"] = V1_GENERIC.get(generic) or (enterprise + ".0." + str(specific))
        result["varbinds"]=_varbinds(p[5][1])
    if not result["trap_oid"]: raise TrapError("trap OID missing")
    return result

def classify(parsed):
    return STD_TRAPS.get(parsed.get("trap_oid"), ("ENTERPRISE_TRAP", "INFO"))

class Collector:
    def __init__(self, manager, bind="0.0.0.0", port=5162, queue_size=256):
        self.manager=manager; self.bind=bind; self.port=int(port)
        self.queue=queue.Queue(maxsize=max(1,int(queue_size)))
        self._sock=None; self._running=False; self._threads=[]
        self.total_packets=0; self.accepted=0; self.rejected=0; self.dropped=0; self.repolls=0
        self.last_error=None; self._last_repoll={}
    def start(self):
        if self._running: return
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        s.bind((self.bind,self.port)); s.settimeout(.5); self._sock=s; self._running=True
        self._threads=[threading.Thread(target=self._recv,daemon=True),threading.Thread(target=self._work,daemon=True)]
        [t.start() for t in self._threads]
    def stop(self):
        self._running=False
        if self._sock:
            try:self._sock.close()
            except OSError:pass
    def _recv(self):
        while self._running:
            try:data,addr=self._sock.recvfrom(65535)
            except socket.timeout:continue
            except OSError:break
            self.total_packets+=1
            try:self.queue.put_nowait((time.time(),addr[0],addr[1],data))
            except queue.Full:self.dropped+=1
    def _work(self):
        while self._running:
            try:item=self.queue.get(timeout=.5)
            except queue.Empty:continue
            try:self._handle(*item)
            except Exception as exc:self.last_error=str(exc)
            finally:self.queue.task_done()
    def _resolve_interface(self, device, ifindex):
        if not device or not ifindex:return ""
        for row in self.manager.db.get_topology_interfaces(device):
            if str(row.get("ifindex")) == str(ifindex):
                return row.get("ifname") or row.get("ifdescr") or ""
        return ""
    def _handle(self, ts, source, source_port, data):
        try: parsed=parse_packet(data)
        except TrapError as exc:
            self.rejected+=1; self.manager.db.audit("snmp-trap","trap_rejected",source,str(exc)[:300]); return None
        dev=self.manager.device_by_host(source); device=dev["name"] if dev else ""
        event_type,severity=classify(parsed); vb=parsed.get("varbinds") or {}
        ifindex=str(vb.get(IFINDEX) or ""); interface=self._resolve_interface(device,ifindex)
        meta={"protocol":"snmp-trap","version":parsed.get("version"),"uptime_ticks":parsed.get("uptime_ticks"),
              "generic_trap":parsed.get("generic_trap"),"specific_trap":parsed.get("specific_trap"),
              "if_admin_status":vb.get(IFADMIN),"if_oper_status":vb.get(IFOPER),"source_port":source_port}
        msg=(event_type.replace("_"," ").title() + (f" on {interface or 'ifIndex '+ifindex}" if ifindex else ""))
        row=self.manager.events.record(source_type="snmp_trap",source=source,device=device,event_type=event_type,
            severity=severity,interface=interface,ifindex=ifindex,trap_oid=parsed.get("trap_oid",""),message=msg,metadata=meta,now=ts,
            allow_suppression=event_type not in {"LINK_DOWN","LINK_UP"})
        self.accepted+=1
        if device and event_type=="LINK_DOWN":
            self.manager.events.suppress_downstream(device,interface,row["id"],now=ts)
        elif device and event_type=="LINK_UP":
            self.manager.events.clear_upstream(device,interface,now=ts)
        if device and self.manager.settings.get("snmp_trap_targeted_repoll",True):
            debounce=max(0,int(self.manager.settings.get("snmp_trap_repoll_debounce_seconds",30)))
            last=self._last_repoll.get(device,0)
            if ts-last >= debounce:
                self._last_repoll[device]=ts
                try:self.manager.snmp_poll(device); self.repolls+=1
                except Exception:pass
        return row
    def status(self):
        return {"running":self._running,"port":self.port,"queue_depth":self.queue.qsize(),"total_packets":self.total_packets,
                "accepted":self.accepted,"rejected":self.rejected,"dropped":self.dropped,"repolls":self.repolls,"last_error":self.last_error}
