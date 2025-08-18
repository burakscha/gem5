.text
.globl _start

_start:
    # Test 1: SFP (Special Frame Pointer) testleri
    # ===========================================
    
    # sfk_setsfp - SFP'yi 0x1000 olarak ayarla
    li a0, 0x1000
    .word 0x000545AB  # sfk_setsfp rd=a1, rs1=a0
    
    # Sonucu kontrol et (a1'de 0x1000 olmalı)
    li t0, 0x1000
    bne a1, t0, test_failed
    
    # sfk_incsfp - SFP'yi 0x100 artır
    .word 0x100055AB  # sfk_incsfp rd=a1, imm=0x100
    
    # Sonucu kontrol et (a1'de 0x1100 olmalı)
    li t0, 0x1100
    bne a1, t0, test_failed

    # Test 2: Spill/Fill testleri
    # ===========================
    
    # Test verilerini hazırla
    li s0, 0x2000      # Base adres
    li s1, 0xDEADBEEF  # Test değeri 1
    li s2, 0xCAFEBABE  # Test değeri 2
    
    # sfk_spill - İlk değeri sakla
    mv a0, s0          # Base adres
    mv a1, s1          # Değer
    .word 0x00B5002B   # sfk_spill rs1=a0, rs2=a1, offset=0
    
    # sfk_spill - İkinci değeri farklı adrese sakla
    addi a0, s0, 8     # Base + 8
    mv a1, s2          # İkinci değer
    .word 0x00B5002B   # sfk_spill rs1=a0, rs2=a1, offset=0
    
    # Registers'ı temizle (fill'in çalıştığını kanıtlamak için)
    li a1, 0
    li a2, 0
    
    # sfk_fill - İlk değeri geri yükle
    mv a0, s0
    .word 0x000515AB   # sfk_fill rd=a1, rs1=a0, offset=0
    
    # Kontrol et
    bne a1, s1, test_failed
    
    # sfk_fill - İkinci değeri geri yükle
    addi a0, s0, 8
    .word 0x0005162B   # sfk_fill rd=a2, rs1=a0, offset=0
    
    # Kontrol et
    bne a2, s2, test_failed

    # Test 3: Kill testleri
    # =====================
    
    # sfk_kill - İlk adresi temizle
    mv a0, s0
    .word 0x0005202B   # sfk_kill rs1=a0, offset=0
    
    # sfk_fill - Temizlenmiş adresten okuma (0 dönmeli)
    .word 0x000515AB   # sfk_fill rd=a1, rs1=a0, offset=0
    
    # Kontrol et (0 olmalı)
    bnez a1, test_failed
    
    # Başarı!
    li a0, 0           # Exit code = 0 (başarı)
    j exit

test_failed:
    li a0, 1           # Exit code = 1 (hata)

exit:
    li a7, 93          # exit syscall
    ecall