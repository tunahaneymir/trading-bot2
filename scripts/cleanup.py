"""
Cleanup Script
==============

Eski log, state ve backup dosyalarını temizler.

Özellikler:
-----------
- Log rotation (eski logları sil)
- State snapshot temizleme
- Backup retention policy
- Selective cleanup (tarih/boyut bazlı)
- Dry-run modu (test için)

Kullanım:
---------
    python scripts/cleanup.py --days 30 --dry-run
    python scripts/cleanup.py --logs --state --backups

Faz: 6
Versiyon: 1.0.0
"""

import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Tuple


class CleanupManager:
    """
    Cleanup yöneticisi.

    Eski dosyaları temizler, retention policy uygular.
    """

    def __init__(
        self,
        project_root: str = ".",
        dry_run: bool = False,
        logger: logging.Logger = None
    ):
        """
        Cleanup Manager başlatıcı.

        Parametreler:
        ------------
        project_root : str
            Proje kök dizini
        dry_run : bool
            Dry-run modu (sadece göster, silme)
        logger : logging.Logger
            Logger instance
        """
        self.project_root = Path(project_root)
        self.dry_run = dry_run
        self.logger = logger or self._setup_logger()

        # Dizinler
        self.logs_dir = self.project_root / "logs"
        self.state_dir = self.project_root / "state"
        self.backups_dir = self.project_root / "backups"
        self.data_dir = self.project_root / "data"

        # İstatistikler
        self.files_deleted = 0
        self.space_freed_mb = 0.0

    def cleanup_logs(self, days: int = 7) -> Tuple[int, float]:
        """
        Eski log dosyalarını temizle.

        Parametreler:
        ------------
        days : int
            Kaç günden eski loglar silinsin

        Returns:
        --------
        Tuple[int, float]
            (silinen_dosya_sayısı, boşaltılan_alan_mb)
        """
        if not self.logs_dir.exists():
            self.logger.warning(f"Logs dizini bulunamadı: {self.logs_dir}")
            return 0, 0.0

        self.logger.info(f"Logs temizleniyor: {days} günden eski")

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        deleted = 0
        freed_mb = 0.0

        # .log ve .log.* dosyaları
        for log_file in self.logs_dir.rglob("*.log*"):
            if log_file.is_file():
                file_time = datetime.fromtimestamp(log_file.stat().st_mtime, tz=timezone.utc)

                if file_time < cutoff_date:
                    size_mb = log_file.stat().st_size / (1024 * 1024)

                    if self.dry_run:
                        self.logger.info(f"[DRY-RUN] Silinecek: {log_file} ({size_mb:.2f} MB)")
                    else:
                        self.logger.info(f"Siliniyor: {log_file} ({size_mb:.2f} MB)")
                        log_file.unlink()

                    deleted += 1
                    freed_mb += size_mb

        self.logger.info(f"Logs temizlendi: {deleted} dosya, {freed_mb:.2f} MB")
        return deleted, freed_mb

    def cleanup_state_snapshots(self, keep_latest: int = 10) -> Tuple[int, float]:
        """
        Eski state snapshot'larını temizle.

        Parametreler:
        ------------
        keep_latest : int
            En son kaç snapshot korunsun

        Returns:
        --------
        Tuple[int, float]
            (silinen_dosya_sayısı, boşaltılan_alan_mb)
        """
        if not self.state_dir.exists():
            self.logger.warning(f"State dizini bulunamadı: {self.state_dir}")
            return 0, 0.0

        self.logger.info(f"State snapshots temizleniyor: en son {keep_latest} korunacak")

        deleted = 0
        freed_mb = 0.0

        # Snapshot dosyaları (örnek: *.snapshot.json)
        snapshot_files = sorted(
            self.state_dir.glob("*.snapshot.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )

        # En son N'i koru, gerisini sil
        to_delete = snapshot_files[keep_latest:]

        for snapshot_file in to_delete:
            size_mb = snapshot_file.stat().st_size / (1024 * 1024)

            if self.dry_run:
                self.logger.info(f"[DRY-RUN] Silinecek: {snapshot_file} ({size_mb:.2f} MB)")
            else:
                self.logger.info(f"Siliniyor: {snapshot_file} ({size_mb:.2f} MB)")
                snapshot_file.unlink()

            deleted += 1
            freed_mb += size_mb

        self.logger.info(f"State snapshots temizlendi: {deleted} dosya, {freed_mb:.2f} MB")
        return deleted, freed_mb

    def cleanup_backups(self, days: int = 30) -> Tuple[int, float]:
        """
        Eski backup'ları temizle.

        Parametreler:
        ------------
        days : int
            Kaç günden eski backup'lar silinsin

        Returns:
        --------
        Tuple[int, float]
            (silinen_klasör_sayısı, boşaltılan_alan_mb)
        """
        if not self.backups_dir.exists():
            self.logger.warning(f"Backups dizini bulunamadı: {self.backups_dir}")
            return 0, 0.0

        self.logger.info(f"Backups temizleniyor: {days} günden eski")

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        deleted = 0
        freed_mb = 0.0

        # Backup dizinleri (YYYY-MM-DD_HH-MM-SS formatında)
        for backup_dir in self.backups_dir.iterdir():
            if backup_dir.is_dir():
                dir_time = datetime.fromtimestamp(backup_dir.stat().st_mtime, tz=timezone.utc)

                if dir_time < cutoff_date:
                    # Dizin boyutunu hesapla
                    size_mb = sum(
                        f.stat().st_size for f in backup_dir.rglob("*") if f.is_file()
                    ) / (1024 * 1024)

                    if self.dry_run:
                        self.logger.info(f"[DRY-RUN] Silinecek: {backup_dir} ({size_mb:.2f} MB)")
                    else:
                        self.logger.info(f"Siliniyor: {backup_dir} ({size_mb:.2f} MB)")
                        self._remove_directory(backup_dir)

                    deleted += 1
                    freed_mb += size_mb

        self.logger.info(f"Backups temizlendi: {deleted} dizin, {freed_mb:.2f} MB")
        return deleted, freed_mb

    def cleanup_old_data(self, days: int = 90) -> Tuple[int, float]:
        """
        Eski veri dosyalarını temizle (data/raw, data/processed).

        Parametreler:
        ------------
        days : int
            Kaç günden eski veriler silinsin

        Returns:
        --------
        Tuple[int, float]
            (silinen_dosya_sayısı, boşaltılan_alan_mb)
        """
        if not self.data_dir.exists():
            self.logger.warning(f"Data dizini bulunamadı: {self.data_dir}")
            return 0, 0.0

        self.logger.info(f"Eski veri dosyaları temizleniyor: {days} günden eski")

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        deleted = 0
        freed_mb = 0.0

        # Raw ve processed dizinleri
        for data_subdir in ["raw", "processed"]:
            subdir_path = self.data_dir / data_subdir

            if not subdir_path.exists():
                continue

            for data_file in subdir_path.rglob("*"):
                if data_file.is_file():
                    file_time = datetime.fromtimestamp(data_file.stat().st_mtime, tz=timezone.utc)

                    if file_time < cutoff_date:
                        size_mb = data_file.stat().st_size / (1024 * 1024)

                        if self.dry_run:
                            self.logger.info(f"[DRY-RUN] Silinecek: {data_file} ({size_mb:.2f} MB)")
                        else:
                            self.logger.info(f"Siliniyor: {data_file} ({size_mb:.2f} MB)")
                            data_file.unlink()

                        deleted += 1
                        freed_mb += size_mb

        self.logger.info(f"Veri dosyaları temizlendi: {deleted} dosya, {freed_mb:.2f} MB")
        return deleted, freed_mb

    def cleanup_all(
        self,
        log_days: int = 7,
        backup_days: int = 30,
        data_days: int = 90,
        keep_snapshots: int = 10
    ) -> None:
        """
        Tüm temizlik işlemlerini çalıştır.

        Parametreler:
        ------------
        log_days : int
            Log retention (gün)
        backup_days : int
            Backup retention (gün)
        data_days : int
            Data retention (gün)
        keep_snapshots : int
            State snapshot sayısı
        """
        self.logger.info("=" * 60)
        self.logger.info("CLEANUP BAŞLIYOR")
        self.logger.info("=" * 60)

        total_deleted = 0
        total_freed_mb = 0.0

        # Logs
        deleted, freed = self.cleanup_logs(log_days)
        total_deleted += deleted
        total_freed_mb += freed

        # State snapshots
        deleted, freed = self.cleanup_state_snapshots(keep_snapshots)
        total_deleted += deleted
        total_freed_mb += freed

        # Backups
        deleted, freed = self.cleanup_backups(backup_days)
        total_deleted += deleted
        total_freed_mb += freed

        # Data
        deleted, freed = self.cleanup_old_data(data_days)
        total_deleted += deleted
        total_freed_mb += freed

        self.logger.info("=" * 60)
        self.logger.info(f"CLEANUP TAMAMLANDI")
        self.logger.info(f"Toplam: {total_deleted} dosya/dizin, {total_freed_mb:.2f} MB")
        self.logger.info("=" * 60)

    def _remove_directory(self, directory: Path) -> None:
        """Dizini ve içeriğini sil."""
        import shutil
        shutil.rmtree(directory)

    def _setup_logger(self) -> logging.Logger:
        """Logger kurulumu."""
        logger = logging.getLogger("cleanup")
        logger.setLevel(logging.INFO)

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)

        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)

        logger.addHandler(handler)
        return logger


def main():
    """Ana fonksiyon."""
    parser = argparse.ArgumentParser(
        description="Cleanup Script - Eski dosyaları temizle"
    )

    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Log retention (gün, varsayılan: 7)"
    )

    parser.add_argument(
        "--backup-days",
        type=int,
        default=30,
        help="Backup retention (gün, varsayılan: 30)"
    )

    parser.add_argument(
        "--data-days",
        type=int,
        default=90,
        help="Data retention (gün, varsayılan: 90)"
    )

    parser.add_argument(
        "--snapshots",
        type=int,
        default=10,
        help="Korunacak snapshot sayısı (varsayılan: 10)"
    )

    parser.add_argument(
        "--logs",
        action="store_true",
        help="Sadece logları temizle"
    )

    parser.add_argument(
        "--state",
        action="store_true",
        help="Sadece state'i temizle"
    )

    parser.add_argument(
        "--backups",
        action="store_true",
        help="Sadece backup'ları temizle"
    )

    parser.add_argument(
        "--data",
        action="store_true",
        help="Sadece veri dosyalarını temizle"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry-run modu (sadece göster, silme)"
    )

    args = parser.parse_args()

    # Cleanup manager
    cleanup = CleanupManager(dry_run=args.dry_run)

    # Selective cleanup
    if args.logs:
        cleanup.cleanup_logs(args.days)
    elif args.state:
        cleanup.cleanup_state_snapshots(args.snapshots)
    elif args.backups:
        cleanup.cleanup_backups(args.backup_days)
    elif args.data:
        cleanup.cleanup_old_data(args.data_days)
    else:
        # Tümünü temizle
        cleanup.cleanup_all(
            log_days=args.days,
            backup_days=args.backup_days,
            data_days=args.data_days,
            keep_snapshots=args.snapshots
        )


if __name__ == "__main__":
    main()
