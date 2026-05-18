import P from "pino";
import * as QRCode from "qrcode";
import dotenv from "dotenv";
import { SpeechClient } from "@google-cloud/speech";
import {
  makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  WASocket,
  AuthenticationState,
  downloadMediaMessage,
  getContentType,
  fetchLatestBaileysVersion
} from "@whiskeysockets/baileys";


//import makeWASocket, { downloadMediaMessage } from "@whiskeysockets/baileys"
import { createWriteStream, readFileSync, unlinkSync } from "fs";
import { promises as fs } from "fs";
import { spawn } from "child_process";


import { rmSync, existsSync } from "fs";
import { join, resolve } from "path";
import { tmpdir } from "os";

const envPath = resolve(__dirname, "../../ros_line/resource/.env");
dotenv.config({ path: envPath });

if (process.env.GOOGLE_APPLICATION_CREDENTIALS?.startsWith("~")) {
  process.env.GOOGLE_APPLICATION_CREDENTIALS = process.env.GOOGLE_APPLICATION_CREDENTIALS.replace(
    /^~/,
    process.env.HOME || ""
  );
}


function fileToBase64(path: string): string {
  const fileBuffer = readFileSync(path);
  return fileBuffer.toString('base64');
}

function deleteFileIfExists(path: string): void {
  try {
    unlinkSync(path);
  } catch {
    // Ignore cleanup errors.
  }
}

function runCommand(command: string, args: string[]): Promise<void> {
  return new Promise((resolve, reject) => {
    const childProcess = spawn(command, args, { stdio: ["ignore", "ignore", "pipe"] });
    let stderr = "";

    childProcess.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    childProcess.on("error", reject);
    childProcess.on("close", (exitCode) => {
      if (exitCode === 0) {
        resolve();
        return;
      }

      reject(new Error(`${command} failed with exit code ${exitCode}: ${stderr}`));
    });
  });
}

function getSpeechEncodingFromMimeType(mimeType: string): string {
  if (mimeType.includes("ogg")) {
    return "OGG_OPUS";
  }
  if (mimeType.includes("mpeg") || mimeType.includes("mp3")) {
    return "MP3";
  }
  if (mimeType.includes("webm")) {
    return "WEBM_OPUS";
  }
  return "ENCODING_UNSPECIFIED";
}


class WhatsAppHandler {
  private sock!: WASocket;
  private readonly speechClient = new SpeechClient();
  private qrAttempts = 0;
  private readonly maxQrAttempts = 3;
  private saveCreds: () => Promise<void> | null;
  //private readonly restartSock: () => Promise<void>;
  private authState: AuthenticationState | undefined;

  async initSocket() {
    console.log("🔄 Inicializando socket de WhatsApp...");
    const { state: newState, saveCreds: newSaveCreds } =
      await useMultiFileAuthState("auth_info_baileys");
    this.authState = newState;
    this.saveCreds = newSaveCreds;

    const { version } = await fetchLatestBaileysVersion();

    this.sock = makeWASocket({
      version,                      
      printQRInTerminal: false,    
      auth: this.authState,
      browser: ["Ubuntu", "Chrome", "22.04.4"],
      syncFullHistory: false,
    });
    this.sock.ev.on("creds.update", this.onCredsUpdate.bind(this));
    this.sock.ev.on("messages.upsert", this.onMessagesUpsert.bind(this));
    this.sock.ev.on("connection.update", this.onConnectionUpdate.bind(this));
  }

  async initSaveCredentials() {}

  constructor() {
    // Bind methods to this instance
    this.saveCreds = async () => {};
    this.onCredsUpdate = this.onCredsUpdate.bind(this);
    this.onMessagesUpsert = this.onMessagesUpsert.bind(this);
    this.onConnectionUpdate = this.onConnectionUpdate.bind(this);
  }

  onCredsUpdate(q: any) {
    console.log(
      "--------------------[ onCredsUpdate  ]-------------------------"
    );
    console.log("Credenciales actualizadas:", q);
    console.log("-----------------------------------------------------------");

    this.saveCreds();
  }

  // Helper function to download and save media files
   downloadAndSaveMedia = (stream: any, filepath: string): Promise<void> => {
    return new Promise((resolve, reject) => {
      const writeStream = createWriteStream(filepath);
      stream.pipe(writeStream);
      writeStream.on('finish', () => {
        console.log(`✅ File saved successfully: ${filepath}`);
        resolve();
      });
      writeStream.on('error', (err) => {
        console.error(`❌ Error saving file: ${err}`);
        reject(err);
      });
    });
  }

  async transcribeAudio(filepath: string, mimeType: string): Promise<string> {
    const audioBuffer = readFileSync(filepath);
    const isOpusAudio = mimeType.includes("ogg") || mimeType.includes("opus") || mimeType.includes("webm");
    let transcriptionSource = audioBuffer.toString("base64");
    let configEncoding = getSpeechEncodingFromMimeType(mimeType) as any;
    let sampleRateHertz = isOpusAudio ? 48000 : 16000;

    if (isOpusAudio && existsSync("/usr/bin/ffmpeg")) {
      const wavPath = `${filepath}.wav`;
      await runCommand("ffmpeg", ["-y", "-i", filepath, "-ac", "1", "-ar", "16000", "-f", "wav", wavPath]);
      transcriptionSource = readFileSync(wavPath).toString("base64");
      configEncoding = "LINEAR16";
      sampleRateHertz = 16000;
      deleteFileIfExists(wavPath);
    }

    const [response] = await this.speechClient.recognize({
      audio: {
        content: transcriptionSource,
      },
      config: {
        encoding: configEncoding,
        sampleRateHertz,
        languageCode: process.env.GSPEECH_LANGUAGE_CODE || "es-ES",
        model: process.env.GSPEECH_MODEL || "latest_short",
        useEnhanced: true,
        enableAutomaticPunctuation: true,
      },
    });

    return (
      response.results
        ?.map((result) => result.alternatives?.[0]?.transcript || "")
        .join(" ")
        .trim() || ""
    );
  }

  /**
   * Maneja los mensajes entrantes y los muestra en la consola.
   * @param m - El objeto de mensajes recibido.
   */
  async onMessagesUpsert(message_array: any) {
    console.log("--------------------[ sock.ev.on - messages.upsert ]-------------------------");
    //console.log("message.upsert:", m);
    for (const msg of message_array.messages) {
      console.log("Mensaje recibido:\n", msg);
      if (msg.key.fromMe) {
        console.log("\tIgnorando mensaje enviado por el propio cliente:",msg.key.remoteJid);
        continue; // Ignorar mensajes enviados por el propio cliente
      }
      
      try {
        //----------------------------------------------------------
        // PROCESAR MENSAJE 
        //----------------------------------------------------------
        if (msg.message) {
          console.log("Mensaje recibido de:", msg.key.remoteJid);

          const messageType = getContentType(msg.message);
          console.log("Tipo de mensaje:", messageType);
          let  mime_type = "";
          let filename = "";
          let message = msg.message.imageMessage?.caption ||
                        msg.message.conversation ||
                        msg.message.extendedTextMessage?.text ||
                        "No texto disponible";
          let shouldSendFile = false;
          let transcribedAudio = "";
          
          if (messageType === 'imageMessage') {
            mime_type = msg.message.imageMessage.mimetype;
            filename = join(tmpdir(), "downloaded-image." + mime_type.split('/')[1]);
             
            // download the media as a stream
            const stream = await downloadMediaMessage(
                msg,
                'stream',
                {},
                {
                    logger: P({ level: "silent" }),
                    reuploadRequest: this.sock.updateMediaMessage
                }
            );
    
            // save the image file locally and wait for it to finish
            await this.downloadAndSaveMedia(stream, filename);
            shouldSendFile = true;
          }
          if (messageType === 'audioMessage') {
            mime_type = msg.message.audioMessage.mimetype;
            filename = join(tmpdir(), "downloaded-audio." + mime_type.split('/')[1]);

            const stream = await downloadMediaMessage(
              msg,
              'stream',
              {},
              {
                  logger: P({ level: "silent" }),
                  reuploadRequest: this.sock.updateMediaMessage
              }
            );
  
            // save the audio file locally and wait for it to finish
            await this.downloadAndSaveMedia(stream, filename);

            try {
              transcribedAudio = await this.transcribeAudio(filename, mime_type);
              console.log("🗣️ Audio transcrito:", transcribedAudio || "[vacío]");
              if (transcribedAudio.trim()) {
                message = transcribedAudio;
              } else {
                transcribedAudio = "";
              }
            } catch (error) {
              console.error("❌ Error transcribiendo audio con Google Speech:", error);
              message = "No pude transcribir el audio. Si quieres, reenvíalo como texto.";
            } finally {
              deleteFileIfExists(filename);
            }
          }

          console.log(
            "Contenido del mensaje:",
            msg.message.conversation ||
              msg.message.extendedTextMessage?.text ||
              "No texto disponible"
          );

          this.sock.readMessages([msg.key]);

          console.log("🔄 Enviando mensaje a la API...");
          console.log("📤 Payload:", {
            message: message,
            user_id: msg.key.remoteJid,
            mime_type: mime_type,
            has_file: shouldSendFile,
            transcribed_audio: !!transcribedAudio
          });

          // Crear AbortController para timeout
          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 segundos timeout

          fetch("http://127.0.0.1:8000/api/chat_v1.1", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              message: message,
              user_id: msg.key.remoteJid,
                mime_type: shouldSendFile ? mime_type || null : null,
                file_base64: shouldSendFile ? fileToBase64(filename) : null
            }),
            redirect: "follow",
            signal: controller.signal
          })
            .then(async (response) => {
              clearTimeout(timeoutId);
              console.log("📥 Respuesta recibida, status:", response.status);
              
              if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
              }
              
              const responseData = await response.json();
              console.log("✅ API response exitosa:", responseData);
              return responseData;
            })
            .then((response: any) => {
              const replyText = response.reply ?? "⚠️ No pude entender tu mensaje - juriel";
              
              console.log("📲 Enviando respuesta a WhatsApp:", replyText);
              
              this.sock.sendMessage(msg.key.remoteJid, {
                text: replyText,
              });
              
              console.log("✅ Mensaje enviado exitosamente");
            })
            .catch((error) => {
              clearTimeout(timeoutId);
              console.error("❌ Error en la comunicación con la API:", error);
              
              let errorMessage = "⚠️ Error interno del sistema";
              
              if (error.name === 'AbortError') {
                errorMessage = "⏱️ Timeout: El servidor tardó demasiado en responder";
              } else if (error.message.includes('ECONNREFUSED')) {
                errorMessage = "🔌 Error de conexión: El servidor no está disponible";
              } else if (error.message.includes('HTTP error')) {
                errorMessage = "🚫 Error del servidor: " + error.message;
              }
              
              // Enviar mensaje de error al usuario
              this.sock.sendMessage(msg.key.remoteJid, {
                text: errorMessage,
              });
            });
        }
      } catch (error) {
        console.log(error);
        console.error("Error al obtener el ID del mensaje:", msg);
      }
      console.log(
        "- - - - - - - - - - -  - - - - - - - - - - - - - - - - - - - - - "
      );
    }
    //console.log("Messages:", m.messages);
    console.log("-----------------------------------------------------------");
  }
  async onConnectionUpdateQR(qr: string) {
    this.qrAttempts++;
    if (this.qrAttempts > this.maxQrAttempts) {
      console.log(
        "❌ Demasiados intentos de escaneo de QR. Cerrando conexión..."
      );
      await this.sock.logout();
      process.exit(1);
      return;
    }

    QRCode.toString(qr, { type: "terminal", small: true }, (err, url) => {
      if (err) return console.error("Error generating QR:", err);
      console.log(url);
      console.log(
        `📱 Escanea el código QR (${this.qrAttempts}/${this.maxQrAttempts})`
      );
    });
  }

  async onConnectionUpdateClose(
    connection: string | undefined,
    lastDisconnect: { error: any } | undefined
  ) {
    console.log(
      "❌ Conexión cerrada",
      (lastDisconnect?.error as any)?.output?.statusCode
    );
    const shouldReconnect =
      (lastDisconnect?.error as any)?.output?.statusCode !==
      DisconnectReason.loggedOut;
    console.log(
      "⚠️ Desconectado de WhatsApp reconnect",
      shouldReconnect,
      "Error:",
      lastDisconnect?.error
    );
    if (shouldReconnect) {
      console.log("🔁 Reintentando conexión...");
      try {
        await this.initSocket(); // Reconectar
      } catch (err) {
        console.error("❌ Error reconectando:", err);
        process.exit(1);
      }
    } else {
      console.log("🚪 Sesión cerrada");
      this.deleteAuthFolder("auth_info_baileys");
      process.exit(0);
      //this.restartSock();
    }
  }
  async onConnectionUpdate(update: {
    connection?: string;
    lastDisconnect?: { error: any };
    qr?: string;
  }) {
    console.log(
      "--------------------[ sock.ev.on - connection.update ]-------------------------"
    );
    console.log("Connection update:", update);
    console.log("-----------------------------------------------------------");

    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      this.onConnectionUpdateQR(qr);
    }

    if (connection === "open") {
      console.log("✅ Conectado a WhatsApp");
    } else if (connection === "close") {
      this.onConnectionUpdateClose(connection, lastDisconnect);
    }
  }

  deleteAuthFolder(folderName: string) {
    const fullPath = join(process.cwd(), folderName);
    console.log(`🗑️ Eliminando carpeta de autenticación: ${fullPath}`);
    if (existsSync(fullPath)) {
      rmSync(fullPath, { recursive: true, force: true });
      console.log(`🗑️ Carpeta "${folderName}" eliminada correctamente.`);
    } else {
      console.log(`⚠️ La carpeta "${folderName}" no existe.`);
    }
  }
}

export { WhatsAppHandler };
