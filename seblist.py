import asyncio
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import os

# === KONFIGURASI ===
api_id = 25851397  # Ganti dengan milikmu dari my.telegram.org
api_hash = '4670283e1f76ed69b3b5c1be60d9e26f'
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
async def forward_job(user_id, mode, source, message_id_or_text, jumlah_grup, durasi_jam, jumlah_pesan):
start = datetime.now()
end = start + timedelta(hours=durasi_jam)
jeda_batch = delay_setting.get(user_id, 5)

now = datetime.now()  
next_reset = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)  
harian_counter = 0  
total_counter = 0  

print(f"[{now:%H:%M:%S}] [INFO] Mulai meneruskan pesan selama {durasi_jam} jam.")  
await client.send_message(user_id, f"Sedang meneruskan pesan...\nDurasi: {durasi_jam} jam\nTarget harian: {jumlah_pesan} pesan.")  

while datetime.now() < end:  
    if datetime.now() >= next_reset:  
        harian_counter = 0  
        next_reset += timedelta(days=1)  
        print(f"[{datetime.now():%H:%M:%S}] [INFO] Reset harian. Melanjutkan pengiriman hari berikutnya.")  

    counter = 0  
    async for dialog in client.iter_dialogs():  
        if datetime.now() >= end:  
            break  
        if harian_counter >= jumlah_pesan:  
            break  
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
            harian_counter += 1  
            total_counter += 1  
            print(f"[{datetime.now():%H:%M:%S}] [BERHASIL] Dikirim ke grup: {dialog.name}")  

            if counter >= jumlah_grup or harian_counter >= jumlah_pesan:  
                break  

        except Exception as e:  
            print(f"[{datetime.now():%H:%M:%S}] [ERROR] Gagal kirim ke {dialog.name}: {e}")  
            continue  

    if harian_counter >= jumlah_pesan:  
        notif = f"Target harian {jumlah_pesan} pesan tercapai.\nBot akan lanjut besok pada jam yang sama, sayangg!"  
        print(f"[{datetime.now():%H:%M:%S}] [INFO] {notif}")  
        await client.send_message(user_id, notif)  

        # Tunggu sampai hari berikutnya (next_reset)  
        sleep_seconds = (next_reset - datetime.now()).total_seconds()  
        await asyncio.sleep(sleep_seconds)  
    else:  
        print(f"[{datetime.now():%H:%M:%S}] [INFO] Batch {counter} grup selesai. Jeda {jeda_batch} detik...")  
        await asyncio.sleep(jeda_batch)  

selesai = f"Forward selesai!\nTotal terkirim ke {total_counter} grup selama {durasi_jam} jam."  
print(f"[{datetime.now():%H:%M:%S}] [INFO] {selesai}")  
await client.send_message(user_id, selesai)

# === PERINTAH ===
@client.on(events.NewMessage(pattern='/scheduleforward'))
async def schedule_cmd(event):
    args = event.message.message.split(maxsplit=2)
    if len(args) < 3:
        return await event.respond("Format salah:\n/scheduleforward text Halo! 10 2 5 300 senin,jumat 08:00")

    try:
        mode = args[1]
        sisa = args[2].rsplit(" ", 6)
        if len(sisa) != 7:
            return await event.respond("Format tidak sesuai. Pastikan argumen lengkap.")

        isi_pesan, jumlah, durasi, jeda, jumlah_pesan, hari_str, waktu = sisa
        jumlah = int(jumlah)
        durasi = int(durasi)
        jeda = int(jeda)
        jumlah_pesan = int(jumlah_pesan)
        jam, menit = map(int, waktu.split(":"))
        hari_list = [HARI_MAPPING.get(h.lower()) for h in hari_str.split(",")]

        if None in hari_list:
            return await event.respond("Ada nama hari yang tidak valid. Gunakan: senin-minggu.")

        for hari_eng in hari_list:
            job_id = f"{event.sender_id}{hari_eng}{datetime.now().timestamp()}"
            job_data[job_id] = {
                "user": event.sender_id, "mode": mode, "source": "",
                "message": isi_pesan, "jumlah": jumlah,
                "durasi": durasi, "jeda": jeda, "jumlah_pesan": jumlah_pesan
            }

            delay_setting[event.sender_id] = jeda

            scheduler.add_job(
                forward_job,
                trigger=CronTrigger(day_of_week=hari_eng, hour=jam, minute=menit),
                args=[event.sender_id, mode, "", isi_pesan, jumlah, durasi, jumlah_pesan],
                id=job_id
            )

        daftar_hari = ", ".join(hari_str.title().split(","))
        await event.respond(f"Jadwal ditambahkan untuk hari {daftar_hari} pukul {waktu}.")

    except Exception as e:
        await event.respond(f"Error: {e}")

@client.on(events.NewMessage(pattern='/forward'))
async def forward_sekarang(event):
    args = event.message.message.split(maxsplit=7)
    if len(args) < 7:
        return await event.respond("Format salah:\n/forward forward @channel 5 12345 5 2 300")

    try:
        mode = args[1]

        if mode == "forward":
            source = args[2]
            jumlah = int(args[3])
            message_id = int(args[4])
            jeda_batch = int(args[5])
            durasi = int(args[6])
            jumlah_pesan = int(args[7]) if len(args) >= 8 else 300

            delay_setting[event.sender_id] = jeda_batch
            await forward_job(event.sender_id, mode, source, message_id, jumlah, durasi, jumlah_pesan)

        elif mode == "text":
            text = args[2]
            jumlah = int(args[3])
            jeda_batch = int(args[4])
            durasi = int(args[5])
            jumlah_pesan = int(args[6]) if len(args) >= 7 else 300

            delay_setting[event.sender_id] = jeda_batch
            pesan_simpan[event.sender_id] = text
            await forward_job(event.sender_id, mode, "", text, jumlah, durasi, jumlah_pesan)

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

@client.on(events.NewMessage(pattern='/ping'))
async def ping(event):
    await event.respond("Bot aktif dan siap melayani!")

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

@client.on(events.NewMessage(pattern='/start'))
async def start_cmd(event):
    teks = (
        "Hai! Aku userbot Heartie! Siap bantu forward otomatis ke grup-grup kamu!\n\n"
        "Gunakan perintah berikut:\n"
        "- /forward — Langsung kirim pesan\n"
        "- /scheduleforward — Jadwalkan kirim pesan mingguan\n"
        "- /help — Lihat panduan lengkap\n\n"
        "Contoh cepat:\n"
        "/forward text Halo semua! 10 5 2 300\n"
        "/scheduleforward forward @channel 10 12345 5 300 senin,jumat 08:00\n\n"
        "Ketik /help untuk info lengkap yaa!"
    )
    await event.respond(teks)

@client.on(events.NewMessage(pattern='/info'))
async def info(event):
    teks = (
        "🤖 Info Bot:\n"
        "- Nama: Heartie Bot\n"
        "- Versi: 1.0\n"
        "- Fungsi: Forward otomatis ke grup.\n"
        "Gunakan /help untuk panduan lengkap."
    )
    await event.respond(teks)

@client.on(events.NewMessage(pattern='/stop'))
async def stop(event):
    try:
        scheduler.shutdown(wait=False)
        await event.respond("Semua jadwal forward telah dihentikan.")
    except Exception as e:
        await event.respond(f"Gagal menghentikan jadwal: {e}")

@client.on(events.NewMessage(pattern='/restart'))
async def restart(event):
    await event.respond("Bot akan restart...")
    os.execv(_file_, [''])

@client.on(events.NewMessage(pattern='/log'))
async def log(event):
    try:
        with open("bot.log", "r") as log_file:
            logs = log_file.read()
            await event.respond(f"📜 Log Terbaru:\n{logs}")
    except FileNotFoundError:
        await event.respond("Log tidak ditemukan.")

@client.on(events.NewMessage(pattern='/feedback'))
async def feedback(event):
    try:
        feedback_message = event.message.message.split(maxsplit=1)[1]
        # Kirim feedback ke admin melalui chat ID tertentu
        admin_chat_id = 1538087933  # Ganti dengan chat ID admin
        await client.send_message(admin_chat_id, f"Feedback dari {event.sender_id}:\n{feedback_message}")
        await event.respond("Terima kasih atas feedback Anda!")
    except IndexError:
        await event.respond("Format salah! Gunakan: /feedback <pesan>")

@client.on(events.NewMessage(pattern='/help'))
async def help_cmd(event):
    teks = """
✨ PANDUAN USERBOT HEARTIE ✨

Haii! Aku userbot Heartie milik kamu, siap bantu sebar-sebar pesan ke grup dengan gaya dan cinta~  
Yuk intip jurus-jurus cintaku:

============================
1. /forward
Langsung kirim pesan ke grup tanpa jadwal!

Mode forward (dari channel):
/forward forward @namachannel jumlah_grup id_pesan jeda detik durasi jam jumlah_pesan_perhari  
Contoh:  
/forward forward @usnchannel 50 27 5 3 300

Mode text (kirim teks langsung):  
/forward text isipesan jumlah_grup jeda detik durasi jam jumlah_pesan_perhari  
Contoh:  
/forward text Halo semua! 50 5 3 300

============================
2. /scheduleforward
Jadwalin pesan mingguan otomatis~

Format umum:  
/scheduleforward mode sumber/pesan jumlah_grup durasi jeda jumlah_pesan_perhari hari,hari jam

Contoh mode forward:  
/scheduleforward forward @usnchannel 20 2 5 300 senin,jumat 08:00

Contoh mode text:  
/scheduleforward text Halo dari bot! 30 3 5 300 selasa,rabu 10:00

============================
3. Preset dan Kontrol Pesan
- /review_pesan — Lihat isi pesan default  
- /ubah_pesan <pesan_baru> — Ganti isi pesan default  
- /simpan_preset <nama> <pesan> — Simpan preset pesan  
- /pakai_preset <nama> — Gunakan preset  
- /list_preset — Lihat semua preset  
- /edit_preset <nama> <pesan_baru> — Edit preset  
- /hapus_preset <nama> — Hapus preset
- /stop — Menghentikan semua jaddwal forward yang sedang berjalan

============================
4. Jadwal dan Delay
- /review — Lihat semua jadwal aktif  
- /deletejob <id> — Hapus jadwal by ID  
- /setdelay <detik> — Atur jeda antar batch kirim  

============================
5. Blacklist Grup
- /blacklist_add <namagrup> — Tambahkan grup ke blacklist  
- /blacklist_remove <namagrup> — Keluarkan dari blacklist  
- /list_blacklist — Lihat daftar blacklist  

============================
6. Info & Bantuan
- /status — Cek masa aktif akun kamu  
- /help — Tampilkan panduan ini  
- /ping — Buat periksa apakah bot udah aktif & responsif
- /info — Cek info dasar dari bot
- /restart — Untuk merestart bot
- /log — Melihat log aktivitas bot terbaru
- /feedback <pesan> — Mengirim umpan balik (feedback) ke pengembang bot

============================

💗 Sefruit Tips:  
Gimana dapetin ID pesan channel buat mode forward?  
Gampang seng! Tinggal klik kanan / tap lama pesan di channel → Salin Link.  
Contoh: https://t.me/usnchannel/19 → ID pesan = 19

---

Selamat menyebar pesan cinta ke seluruh penjuru grup~  
Kalau ada yang bingung, tinggal tanya admin Zero/bot HeartHeart. Dia siap bantu kapan pun, sayangg~!
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
    return "Eastorn Bot is alive!"

def keep_alive():
    app.run(host="0.0.0.0", port=8080)

# Jalankan Flask server di thread terpisah
threading.Thread(target=keep_alive).start()
