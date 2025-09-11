# VID Manager

`VIDManager` จัดการการสร้างและเชื่อมโยง Vehicle Identifier (VID) ภายในระบบ
โดยจะแปลงข้อมูลระบุตัวตนภายนอก เช่น MacID, idTag หรือหมายเลขโทรศัพท์
ให้เป็น VID รูปแบบ `VID:XXXXXXXXXX` ที่ใช้ภายในเซิร์ฟเวอร์เดียวกัน

## การใช้งานพื้นฐาน

```python
from services.vid_manager import VIDManager

vm = VIDManager()

# สร้างหรือค้นหา VID จาก idTag
vid = vm.get_or_create_vid("id_tag", "ABCD1234")

# เชื่อมโยง VID ชั่วคราวกับ VID ถาวร
vm.link_temp_vid("VID:TEMP001", vid)
```

ฟังก์ชันหลัก

- `get_or_create_vid(source_type, source_value)`
  - รับชนิดของข้อมูลและค่าที่ได้รับจากภายนอก
  - คืนค่า VID ที่เคยสร้างไว้หรือสร้างใหม่หากยังไม่เคยมี
- `link_temp_vid(vid_temp, vid_perm)`
  - รวมข้อมูลทั้งหมดที่เคยผูกกับ `vid_temp` ไปยัง `vid_perm`
  - ใช้เมื่อระบบสร้าง VID ชั่วคราวไว้ก่อนแล้วภายหลังได้ข้อมูลถาวรของรถ

โมดูลนี้ถูกเรียกใช้งานใน workflow ต่าง ๆ ภายในโครงการ เช่น เมื่อได้รับ
ข้อความ Authorize หรือ DataTransfer จากตู้ชาร์จ รวมถึงการสั่งงานผ่าน API
เพื่อให้ทุกการอ้างอิง VID เป็นไปในที่เดียวกัน