using DemoFile;
using DemoFile.Game.Cs;
using System.Text.Json;
using System.Security.Cryptography;

if (args.Length != 2) throw new ArgumentException("Expected demo path and output JSONL path");
using var writer = new StreamWriter(args[1]);
var demo = new CsDemoParser();
var seenSmoke = new Dictionary<string, string>();
var seenDoors = new Dictionary<string, string>();
void Write(object row) => writer.WriteLine(JsonSerializer.Serialize(row));
float[] Vec(Vector v) => new[] { v.X, v.Y, v.Z };
void Smoke(CSmokeGrenadeProjectile smoke) {
    if (smoke.VoxelFrameDataSize <= 0) return;
    var bytes = smoke.VoxelFrameData.ToArray();
    var id = smoke.EntityHandle.ToString();
    var hash = Convert.ToHexString(SHA256.HashData(bytes));
    var signature = $"{smoke.VoxelUpdate}:{smoke.VoxelFrameDataSize}:{hash}";
    if (seenSmoke.GetValueOrDefault(id) == signature) return;
    seenSmoke[id] = signature;
    Write(new { kind="smoke", tick=demo.CurrentDemoTick.Value, entity=id,
        revision=smoke.VoxelUpdate, declared_size=smoke.VoxelFrameDataSize,
        array_size=bytes.Length, sha256=hash, data_base64=Convert.ToBase64String(bytes),
        detonation_position=Vec(smoke.SmokeDetonationPos),
        server_effect_tick=smoke.SmokeEffectTickBegin });
}
void Door(CBasePropDoor door) {
    var id = door.EntityHandle.ToString();
    var pose = new { state=door.DoorState.ToString(), locked=door.Locked,
        origin=Vec(door.Origin), rotation=new[]{door.Rotation.Pitch,door.Rotation.Yaw,door.Rotation.Roll} };
    var signature=JsonSerializer.Serialize(pose);
    if (seenDoors.GetValueOrDefault(id) == signature) return;
    seenDoors[id]=signature;
    Write(new { kind="door", tick=demo.CurrentDemoTick.Value, entity=id, pose });
}
demo.EntityEvents.CSmokeGrenadeProjectile.Create += Smoke;
demo.EntityEvents.CSmokeGrenadeProjectile.PostUpdate += Smoke;
demo.EntityEvents.CBasePropDoor.Create += Door;
demo.EntityEvents.CBasePropDoor.PostUpdate += Door;
demo.EntityEvents.CBasePropDoor.Delete += d => Write(new {kind="door_delete",tick=demo.CurrentDemoTick.Value,entity=d.EntityHandle.ToString()});
demo.EntityEvents.CSmokeGrenadeProjectile.Delete += d => Write(new {kind="smoke_delete",tick=demo.CurrentDemoTick.Value,entity=d.EntityHandle.ToString()});
using var stream=File.OpenRead(args[0]);
var reader=DemoFileReader.Create(demo,stream);
await reader.ReadAllAsync();
Console.WriteLine($"Parsed through tick {demo.CurrentDemoTick}; output: {args[1]}");
