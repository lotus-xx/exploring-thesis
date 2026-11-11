// macOS PDFKit text layer only. Emits all pages as JSON, never infers reading.
#import <Foundation/Foundation.h>
#import <PDFKit/PDFKit.h>

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc != 2 && argc != 3) { fprintf(stderr, "usage: pdfextract file.pdf [pages_csv]\n"); return 2; }
        NSString *path = [NSString stringWithUTF8String:argv[1]];
        PDFDocument *doc = [[PDFDocument alloc] initWithURL:[NSURL fileURLWithPath:path]];
        if (!doc || doc.isLocked || doc.pageCount == 0) {
            fprintf(stderr, "unreadable, locked or empty PDF\n"); return 1;
        }
        NSMutableArray *pages = [NSMutableArray array];
        NSSet *selected = argc==3 ? [NSSet setWithArray:[[NSString stringWithUTF8String:argv[2]] componentsSeparatedByString:@","]] : nil;
        for (NSUInteger i=0; i<doc.pageCount; i++) {
            if (selected && ![selected containsObject:[NSString stringWithFormat:@"%lu",(unsigned long)i+1]]) continue;
            PDFPage *page = [doc pageAtIndex:i];
            NSString *text = page.string ?: @"";
            BOOL nonempty = [text stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet].length > 0;
            [pages addObject:@{@"page":@(i+1), @"text":text,
                @"has_text":@(nonempty), @"error":page ? (id)NSNull.null : @"page unavailable"}];
        }
        NSError *error = nil;
        NSData *data = [NSJSONSerialization dataWithJSONObject:@{@"total_pages":@(doc.pageCount), @"pages":pages}
                                                       options:0 error:&error];
        if (!data) { fprintf(stderr, "JSON serialization failed\n"); return 1; }
        [[NSFileHandle fileHandleWithStandardOutput] writeData:data];
        // Success means PDF structure was read, NOT that body text exists.
        return 0;
    }
}
