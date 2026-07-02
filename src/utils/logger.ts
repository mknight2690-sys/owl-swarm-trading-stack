/** Structured logging for the OWL Swarm */

import winston from "winston";
import path from "node:path";
import fs from "node:fs";

const outputDir = process.env["OUTPUT_DIR"] ?? "outputs";
fs.mkdirSync(outputDir, { recursive: true });

const logFormat = winston.format.combine(
  winston.format.timestamp({ format: "YYYY-MM-DD HH:mm:ss.SSS" }),
  winston.format.errors({ stack: true }),
  winston.format.printf(({ timestamp, level, message, ...meta }) => {
    const metaStr = Object.keys(meta).length > 0 ? ` ${JSON.stringify(meta)}` : "";
    return `[${timestamp}] ${level.toUpperCase().padEnd(7)} ${message}${metaStr}`;
  })
);

export const logger = winston.createLogger({
  level: process.env["LOG_LEVEL"] ?? "info",
  format: logFormat,
  transports: [
    new winston.transports.Console({
      format: winston.format.combine(
        winston.format.colorize(),
        logFormat
      ),
    }),
    new winston.transports.File({
      filename: path.join(outputDir, "swarm.log"),
      maxsize: 10 * 1024 * 1024,
      maxFiles: 5,
    }),
    new winston.transports.File({
      filename: path.join(outputDir, "swarm-error.log"),
      level: "error",
      maxsize: 10 * 1024 * 1024,
      maxFiles: 5,
    }),
  ],
});

export function childLogger(module: string): winston.Logger {
  return logger.child({ module });
}
