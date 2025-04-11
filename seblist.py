import asyncio
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import os

# === KONFIGURASI ===
api_id = 28708516  # Ganti dengan milikmu dari my.telegram.org
api_hash = 'd9cf8f299399789fdb9e5921ebc7831a'
client = TelegramClient("user_session", api_id, api_hash)

# === SCHEDULER ===
scheduler = AsyncIOScheduler()

# === DATA ===
blacklisted_groups = set()
job_data = {}
delay_setting = {}
MASA_AKTIF = datetime(2030, 12, 31)
pesan_simpan = {}  # key: user_id, value: pesan terbaru
preset_pesan = {}  # key: user_id, value: {nama_preset: isi_pesan}

HARI_MAPPING = {
    "senin": "monday", "selasa": "tuesday", "rabu": "wednesday",
    "kamis": "thursday", "jumat": "friday", "sabtu": "saturday", "minggu": "sunday"
}

# === FORWARDING ===
async def forward_job(user_id, mode, source, message_id_or_text, jumlah_grup, durasi_jam):
    start = datetime.now()
    end = start + timedelta(hours=durasi_jam)
    jeda_batch = delay_setting.get(user_id, 5)
    total_counter = 0

    print(f"[{datetime.now():%H:%M:%S}] [INFO] Mulai meneruskan pesan secara berulang selama {durasi_jam} jam.")
    await client.send_message(user_id, f"Sedang meneruskan pesan berulang selama {durasi_jam} jam...")

    while datetime.now() < end:
        counter = 0
        async for dialog in client.iter_dialogs():
            if not dialog.is_group or dialog.name in blacklisted_groups:
                continue
            try:
                if mode == "forward":
                    msg = await client.get_messages(source, ids=int(message_id_or_text))
                    if msg:
                        await client.forward_messages(dialog.id, msg.id, from_peer=source)
                else:
                    await client.send_message(dialog.id, message_id_or_text, link_preview=True)

                counter += 1
                total_counter += 1
                print(f"[{datetime.now():%H:%M:%S}] [BERHASIL] Dikirim ke grup: {dialog.name}")

                if counter >= jumlah_grup:
                    break

            except Exception as e:
                print(f"[{datetime.now():%H:%M:%S}] [ERROR] Gagal kirim ke {dialog.name}: {e}")
                continue

        print(f"[{datetime.now():%H:%M:%S}] [INFO] Batch {counter} grup selesai. Tunggu {jeda_batch} detik...")
        await asyncio.sleep(jeda_batch)

    print(f"[{datetime.now():%H:%M:%S}] [INFO] Forward selesai. Total {total_counter} grup selama {durasi_jam} jam.")
    await client.send_message(user_id, f"Forward selesai. Total dikirim ke {total_counter} grup selama {durasi_jam} jam.")

    # Kirim hasil ke user Telegram
    teks = f"== Forward selesai ==\n\n"
    teks += f"Total berhasil: {len(berhasil_dikirim)}\n"
    teks += f"Total gagal: {len(gagal_dikirim)}\n\n"

    if berhasil_dikirim:
        teks += "== Grup berhasil ==\n" + "\n".join(f"- {g}" for g in berhasil_dikirim[:10])  # Batasi biar ga terlalu panjang
        if len(berhasil_dikirim) > 10:
            teks += f"\n...dan {len(berhasil_dikirim) - 10} grup lainnya."

    if gagal_dikirim:
        teks += "\n\n== Grup gagal ==\n" + "\n".join(f"- {g}" for g in gagal_dikirim[:10])
        if len(gagal_dikirim) > 10:
            teks += f"\n...dan {len(gagal_dikirim) - 10} lainnya."

    await client.send_message(user_id, teks)

# === PERINTAH ===
@client.on(events.NewMessage(pattern='/scheduleforward'))
async def schedule_cmd(event):
    args = event.message.message.split(maxsplit=2)
    if len(args) < 3:
        return await event.respond("Format salah:\n"
                                   "/scheduleforward text <pesan> <jumlah> <durasi> <jeda> <hari> <waktu>\n"
                                   "atau\n"
                                   "/scheduleforward forward @channel <jumlah> <msg_id> <jeda> <durasi> <hari> <waktu>")

    try:
        mode = args[1].lower()

        if mode == "text":
            # Format: /scheduleforward text Halo! 10 2 5 senin,jumat 08:00
            sisa = args[2].rsplit(" ", 5)
            if len(sisa) != 6:
                return await event.respond("Format salah.\nGunakan: /scheduleforward text <pesan> <jumlah> <durasi> <jeda> <hari> <waktu>")

            isi_pesan, jumlah, durasi, jeda, hari_str, waktu = sisa
            jumlah, durasi, jeda = int(jumlah), int(durasi), int(jeda)

            source = ""
            message_id = isi_pesan  # isi pesan teks
        elif mode == "forward":
            # Format: /scheduleforward forward @channel 10 12345 5 2 senin,jumat 08:00
            sisa = args[2].split(" ")
            if len(sisa) != 7:
                return await event.respond("Format salah.\nGunakan: /scheduleforward forward @channel <jumlah> <msg_id> <jeda> <durasi> <hari> <waktu>")

            source, jumlah, message_id, jeda, durasi, hari_str, waktu = sisa
            jumlah, message_id, jeda, durasi = int(jumlah), int(message_id), int(jeda), int(durasi)

        else:
            return await event.respond("Mode harus 'text' atau 'forward'.")

        hari_list = [HARI_MAPPING.get(h.strip().lower()) for h in hari_str.split(",")]
        if None in hari_list:
            return await event.respond("Ada nama hari yang tidak valid. Gunakan: senin-minggu.")

        jam, menit = map(int, waktu.split(":"))

        for hari_eng in hari_list:
            job_id = f"{event.sender_id}{hari_eng}{datetime.now().timestamp()}"

            job_data[job_id] = {
                "user": event.sender_id,
                "mode": mode,
                "source": source,
                "message": message_id,
                "jumlah": jumlah,
                "durasi": durasi,
                "jeda": jeda
            }

            delay_setting[event.sender_id] = jeda

            scheduler.add_job(
                forward_job,
                trigger=CronTrigger(day_of_week=hari_eng, hour=jam, minute=menit),
                args=[event.sender_id, mode, source, message_id, jumlah, durasi],
                id=job_id
            )

        daftar_hari = ", ".join(hari_str.title().split(","))
        await event.respond(f"Jadwal berhasil ditambahkan untuk hari {daftar_hari} pukul {waktu}.")

    except Exception as e:
        await event.respond(f"Error: {e}")

@client.on(events.NewMessage(pattern='/forward'))
async def forward_sekarang(event):
    args = event.message.message.split(maxsplit=6)
    if len(args) < 6:
        return await event.respond("Format salah:\n/forward forward @channel 5 12345 5 2")

    try:
        mode = args[1]
        if mode == "forward":
            source = args[2]
            jumlah = int(args[3])
            message_id = int(args[4])
            delay = int(args[5])
            durasi = int(args[6]) if len(args) >= 7 else 1
            delay_setting[event.sender_id] = delay
            await forward_job(event.sender_id, mode, source, message_id, jumlah, durasi)
        elif mode == "text":
            text = args[2]
            jumlah = int(args[3])
            delay = int(args[5])
            durasi = int(args[6]) if len(args) >= 7 else 1
            delay_setting[event.sender_id] = delay
            pesan_simpan[event.sender_id] = text
            await forward_job(event.sender_id, mode, "", text, jumlah, durasi)
        else:
            await event.respond("Mode harus 'forward' atau 'text'")
    except Exception as e:
        await event.respond(f"Error: {e}")

@client.on(events.NewMessage(pattern='/setdelay'))
async def set_delay(event):
    try:
        delay = int(event.message.message.split()[1])
        delay_setting[event.sender_id] = delay
        await event.respond(f"Jeda antar *batch* diset ke {delay} detik.")
    except:
        await event.respond("Gunakan: /setdelay <detik>")

@client.on(events.NewMessage(pattern='/review'))
async def review_jobs(event):
    teks = "== Jadwal Aktif ==\n"
    if not job_data:
        teks += "Tidak ada jadwal."
    else:
        for job_id, info in job_data.items():
            teks += f"- ID: {job_id}\n  Mode: {info['mode']}\n  Grup: {info['jumlah']}\n  Durasi: {info['durasi']} jam\n"
    await event.respond(teks)

@client.on(events.NewMessage(pattern='/deletejob'))
async def delete_job(event):
    try:
        job_id = event.message.message.split()[1]
        scheduler.remove_job(job_id)
        job_data.pop(job_id, None)
        await event.respond("Jadwal dihapus.")
    except:
        await event.respond("Gagal menghapus.")

@client.on(events.NewMessage(pattern='/blacklist_add'))
async def add_blacklist(event):
    try:
        nama = " ".join(event.message.message.split()[1:])
        blacklisted_groups.add(nama)
        await event.respond(f"'{nama}' masuk blacklist.")
    except:
        await event.respond("Format salah.")

@client.on(events.NewMessage(pattern='/blacklist_remove'))
async def remove_blacklist(event):
    try:
        nama = " ".join(event.message.message.split()[1:])
        blacklisted_groups.discard(nama)
        await event.respond(f"'{nama}' dihapus dari blacklist.")
    except:
        await event.respond("Format salah.")

@client.on(events.NewMessage(pattern='/list_blacklist'))
async def list_blacklist(event):
    if not blacklisted_groups:
        await event.respond("Blacklist kosong.")
    else:
        teks = "== Grup dalam blacklist ==\n"
        teks += "\n".join(blacklisted_groups)
        await event.respond(teks)

@client.on(events.NewMessage(pattern='/status'))
async def cek_status(event):
    now = datetime.now()
    sisa = (MASA_AKTIF - now).days
    tanggal_akhir = MASA_AKTIF.strftime('%d %B %Y')
    await event.respond(
        f"Masa aktif tersisa: {sisa} hari\n"
        f"Userbot aktif sampai: {tanggal_akhir}"
    )

@client.on(events.NewMessage(pattern='/review_pesan'))
async def review_pesan(event):
    pesan = pesan_simpan.get(event.sender_id)
    if not pesan:
        await event.respond("Belum ada pesan yang disimpan.")
    else:
        await event.respond(f"== Isi Pesan Saat Ini ==\n{pesan}")

@client.on(events.NewMessage(pattern='/ubah_pesan'))
async def ubah_pesan(event):
    try:
        teks = event.message.message.split(" ", maxsplit=1)[1]
        pesan_simpan[event.sender_id] = teks
        await event.respond("Isi pesan berhasil diubah.")
    except:
        await event.respond("Format salah. Gunakan:\n/ubah_pesan <pesan_baru>")

@client.on(events.NewMessage(pattern='/simpan_preset'))
async def simpan_preset(event):
    try:
        user_id = event.sender_id
        _, nama, pesan = event.message.message.split(" ", maxsplit=2)
        preset_pesan.setdefault(user_id, {})[nama] = pesan
        await event.respond(f"Preset '{nama}' disimpan.")
    except:
        await event.respond("Format salah.\n/simpan_preset <nama> <pesan>")

@client.on(events.NewMessage(pattern='/pakai_preset'))
async def pakai_preset(event):
    try:
        user_id = event.sender_id
        nama = event.message.message.split(" ", maxsplit=1)[1]
        pesan = preset_pesan.get(user_id, {}).get(nama)
        if not pesan:
            return await event.respond(f"Tidak ada preset dengan nama '{nama}'")
        pesan_simpan[user_id] = pesan
        await event.respond(f"Preset '{nama}' dipilih:\n\n{pesan}")
    except:
        await event.respond("Format salah.\n/pakai_preset <nama>")

@client.on(events.NewMessage(pattern='/list_preset'))
async def list_preset(event):
    user_id = event.sender_id
    daftar = preset_pesan.get(user_id, {})
    if not daftar:
        return await event.respond("Belum ada preset.")
    teks = "== Daftar Preset ==\n"
    for nama in daftar:
        teks += f"- {nama}\n"
    await event.respond(teks)

@client.on(events.NewMessage(pattern='/edit_preset'))
async def edit_preset(event):
    try:
        user_id = event.sender_id
        _, nama, pesan_baru = event.message.message.split(" ", maxsplit=2)
        if nama not in preset_pesan.get(user_id, {}):
            return await event.respond(f"Tidak ada preset dengan nama '{nama}'")
        preset_pesan[user_id][nama] = pesan_baru
        await event.respond(f"Preset '{nama}' berhasil diubah.")
    except:
        await event.respond("Format salah.\n/edit_preset <nama> <pesan_baru>")

@client.on(events.NewMessage(pattern='/hapus_preset'))
async def hapus_preset(event):
    try:
        user_id = event.sender_id
        nama = event.message.message.split(" ", maxsplit=1)[1]
        if nama in preset_pesan.get(user_id, {}):
            del preset_pesan[user_id][nama]
            await event.respond(f"Preset '{nama}' dihapus.")
        else:
            await event.respond(f"Preset '{nama}' tidak ditemukan.")
    except:
        await event.respond("Format salah.\n/hapus_preset <nama>")

@client.on(events.NewMessage(pattern='/help'))
async def help_cmd(event):
    teks = """
== FITUR UTAMA USERBOT ==

/forward forward @channel jumlah_grup id_pesan durasi(jam) jeda(detik)
- Forward langsung dari channel ke grup (tanpa jadwal)
- Contoh command: /forward forward @channel 100 27 2 30
- Maka pesan dari channel yang dituju akan meneruskan pesan ke 100 grup dengan id pesan 27 selama 2 jam dengan jeda 30 detik

/forward text <pesan> jumlah_grup durasi(jam) jeda(detik)
- Kirim teks langsung ke grup (tanpa jadwal)
- Contoh command: /forward text Halo, ini adalah pesan diteruskan. 20 4 30

/scheduleforward mode @channel jumlah_grup id/isi_pesan durasi(jam) jeda(detik) hari jam
- Jadwalkan forward setiap minggu
- Mode: forward atau text
- Contoh command mode forward: /scheduleforward forward @channel 20 2 8 30 senin,rabu,jumat 19:00
- Command untuk mode text: /scheduleforward text <pesan> jumlah_grup durasi(jam) jeda(detik) hari jam
- Contoh command mode text: /scheduleforward text Halo, ini adalah pesan diteruskan. 30 24 60 selasa,sabtu 08:00

/setdelay 10
- Atur jeda antar pesan (detik)

/review_pesan
- Lihat isi pesan terbaru (mode text)

/ubah_pesan <pesan_baru>
- Ubah isi pesan terbaru sebelum dikirim

/simpan_preset <nama> <pesan>
- Simpan pesan sebagai preset

/pakai_preset <nama>
- Gunakan preset yang sudah disimpan

/list_preset
- Lihat semua preset pesan

/edit_preset <nama> <pesan_baru>
- Ubah isi preset yang sudah disimpan

/hapus_preset <nama>
- Hapus preset berdasarkan nama

/review
- Lihat daftar jadwal

/deletejob <id>
- Hapus jadwal tertentu

/status
- Cek masa aktif lisensi

/blacklist_add <nama>
- Tambahkan grup untuk diblacklist dengan nama grup

/blacklist_remove <nama>
- Hapus grup yang diblacklist dengan nama grup

/list_blacklist
- Kelola grup yang diblacklist

/help
- Tampilkan perintah

Mungkin beberapa dari kalian ada yang belum tahu:
🗣️: Min, gimana cara tau id pesan?
👤: Tinggal ke pesan yang pengen disebar, klik sebelah bubble chat (bagian space kosong) terus copy link pesannya
nanti tampilannya kan bakal kaya gini https://t.me/usnchannel/19 nah angka yang paling akhir itu id pesannya. Tinggal masukkin angkanya aja ke command.
"""
    await event.respond(teks)

# === LISENSI ===
async def cek_lisensi():
    if datetime.now() > MASA_AKTIF:
        print("Lisensi expired.")
        exit()

# === JALANKAN BOT ===
async def main():
    await client.start()
    scheduler.start()  # <- sekarang aman karena sudah dalam event loop
    await cek_lisensi()
    me = await client.get_me()
    print(f"Bot aktif, anda masuk sebagai {me.first_name}. Menunggu perintah...")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())

# Tambahan agar Railway tetap aktif via UptimeRobot
from flask import Flask
import threading

app = Flask(_name_)

@app.route('/')
def home():
    return "Vine Bot is alive!"

def keep_alive():
    app.run(host="0.0.0.0", port=8080)

# Jalankan Flask server di thread terpisah
threading.Thread(target=keep_alive).start()
