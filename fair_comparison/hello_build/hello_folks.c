#include <stdio.h>
#include <gem5/m5ops.h>

int main() {
    // ROI START: Region of Interest for spill detection
    m5_work_begin(0, 0);
    
    printf("hello f0lks!\n");
    
    m5_work_end(0, 0);
    // ROI END: Region of Interest for spill detection
    return 0;
}
